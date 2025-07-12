#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Standardbibliotheken
import argparse
import asyncio
import os
import re
import shutil
import unicodedata
import logging
import time
from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache, wraps, partial  # Hinzugefügt für besseres Caching
import json  # Für Serialisierung von Dicts
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    TypedDict,
    Callable,
    Set,
    FrozenSet,
)
from dataclasses import (
    dataclass,
    field,
)  # Implementierung von Verbesserungsvorschlag #5
from collections import Counter  # Für LFU Cache Implementierung

# Externe Abhängigkeiten
import mutagen
from mutagen.mp4 import MP4, MP4Cover
from mutagen import MutagenError

# Lokale Module
from config import Config
from logger import log_error
from helfer.artist_map import ARTIST_GENRE_MAP

# Logger konfigurieren - Verbesserungsvorschlag #10
logger = logging.getLogger(__name__)

# ---------------------------
# Datei- und Namensoperationen
# ---------------------------

# Implementierung von Verbesserungsvorschlag #7: Pattern-Kompilierung
FEAT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\((feat\.|ft\.|with)\s(.+?)\)",
        r"feat[\.\s]+([^)]+)",
        r"ft[\.\s]+([^)]+)",
        r"featuring\s+([^)]+)",
        r"&\s+([^)]+)",
    ]
]

# Verbesserungsvorschlag #4: Konsistente Regex-Nutzung
TRACK_NUMBER_PATTERN = re.compile(r"(\d+)")

# String Pattern für Dateinamenbereinigung
ILLEGAL_CHARS_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
FEAT_NOTATION_PATTERN = re.compile(r"\s*\(feat\.\s+([^)]+)\)")
EXTRA_SPACES_PATTERN = re.compile(r"\s+")

# Artist Patterns
ARTIST_CLEANUP_PATTERN = re.compile(
    r"( - Topic| - .*Official.*|VEVO|Official.*|\(.*\)|\[.*\]|\s*-\s*$)", re.IGNORECASE
)
ARTIST_SPLIT_PATTERN = re.compile(r"[,x&]|feat\.?")

# Albumnamen-Patterns (Verbesserungsvorschlag #4)
ALBUM_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"album\s*[:\-?]\s*(.+?)(?:\n|$)",
        r"from the album\s+['\"]?(.+?)['\"]?(?:\n|$)",
        r"aus dem album\s+['\"]?(.+?)['\"]?(?:\n|$)",
    ]
]


# Implementierung von Verbesserungsvorschlag #1: Dynamische Cache-Größe
class DynamicLRUCache:
    def __init__(self, initial_size=1024, growth_factor=1.2, max_size=5000):
        self.size = initial_size
        self.growth_factor = growth_factor
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.last_resize = time.time()
        self.check_interval = 60  # Sekunden zwischen Anpassungen

    def decorator(self, func):
        # Erstelle einen partiellen LRU Cache mit der aktuellen Größe
        cached_func = lru_cache(maxsize=self.size)(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            result = cached_func(*args, **kwargs)

            # Hit/Miss Statistik aktualisieren (basierend auf Cache Info)
            info = cached_func.cache_info()
            self.hits = info.hits
            self.misses = info.misses

            # Bei Bedarf Cache-Größe anpassen
            self._adjust_size_if_needed(cached_func)

            return result

        # Zugängliche Statistiken und Funktionen
        wrapper.cache_info = cached_func.cache_info
        wrapper.cache_clear = cached_func.cache_clear
        wrapper.resize = lambda new_size: self._resize_cache(cached_func, new_size)

        return wrapper

    def _adjust_size_if_needed(self, cached_func):
        """Passt die Cache-Größe basierend auf Hit/Miss-Rate an"""
        now = time.time()
        if now - self.last_resize < self.check_interval:
            return

        self.last_resize = now

        # Berechne Hit-Rate
        total = self.hits + self.misses
        if total < 100:  # Zu wenig Daten für Anpassung
            return

        hit_rate = self.hits / total if total > 0 else 0

        # Reduziere bei hoher Hit-Rate
        if hit_rate > 0.9 and self.size > 100:
            new_size = max(100, int(self.size / self.growth_factor))
            self._resize_cache(cached_func, new_size)
        # Erhöhe bei niedriger Hit-Rate
        elif hit_rate < 0.7:
            new_size = min(self.max_size, int(self.size * self.growth_factor))
            self._resize_cache(cached_func, new_size)

    def _resize_cache(self, cached_func, new_size):
        """Cache-Größe anpassen (nur möglich durch Neuerstellen des Caches)"""
        if new_size == self.size:
            return

        logger.debug(f"Passe Cache-Größe an: {self.size} -> {new_size}")
        self.size = new_size

        # Cache-Objekt ersetzen - leider ist das mit dem LRU Cache nicht direkt möglich,
        # aber wir können die Funktion neu cachen
        cached_func.cache_clear()
        # Theoretisch müssten wir hier den Decorator neu anwenden, aber das ist komplex
        # Da es nur um die Größe geht, ist eine Löschung auch akzeptabel


# Verbesserungsvorschlag #1: LFU Cache implementieren
class LFUCache:
    """Least Frequently Used (LFU) Cache Implementierung"""

    def __init__(self, maxsize=1024):
        self.maxsize = maxsize
        self.cache = {}
        self.key_count = Counter()
        self.sentinel = object()  # Für Cache-Miss Erkennung

    def _make_key(self, args, kwargs):
        """Erstellt einen hashbaren Schlüssel aus Funktionsargumenten"""
        key_parts = []

        # Verarbeite normale Argumente
        for arg in args:
            if isinstance(arg, dict):
                # Dictionaries sind nicht hashbar
                arg_key = frozenset((k, self._make_hashable(v)) for k, v in arg.items())
            elif isinstance(arg, list):
                # Listen sind nicht hashbar
                arg_key = tuple(self._make_hashable(v) for v in arg)
            else:
                arg_key = arg
            key_parts.append(arg_key)

        # Verarbeite Keyword-Argumente
        kw_parts = []
        for k, v in sorted(kwargs.items()):
            kw_parts.append((k, self._make_hashable(v)))
        key_parts.append(tuple(kw_parts))

        return hash(tuple(key_parts))

    def _make_hashable(self, obj):
        """Konvertiert unhashbare Objekte zu hashbaren Repräsentationen"""
        if isinstance(obj, dict):
            return frozenset((k, self._make_hashable(v)) for k, v in obj.items())
        elif isinstance(obj, list):
            return tuple(self._make_hashable(v) for v in obj)
        elif isinstance(obj, set):
            return frozenset(self._make_hashable(v) for v in obj)
        else:
            return obj

    def decorator(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Erstelle hashbaren Schlüssel
            key = self._make_key(args, kwargs)

            # Prüfe Cache
            result = self.cache.get(key, self.sentinel)
            if result is not self.sentinel:
                # Cache Hit
                self.key_count[key] += 1
                return result

            # Cache Miss
            result = func(*args, **kwargs)

            # Cache aktualisieren
            if len(self.cache) >= self.maxsize:
                # Entferne am wenigsten verwendeten Eintrag
                least_common = self.key_count.most_common()[:-2:-1]
                if least_common:  # Sicherstellen, dass wir einen Eintrag haben
                    lc_key = least_common[0][0]
                    del self.cache[lc_key]
                    del self.key_count[lc_key]

            # Neuen Eintrag hinzufügen
            self.cache[key] = result
            self.key_count[key] = 1

            return result

        # Cache-Operationen zugänglich machen
        wrapper.cache_clear = lambda: (self.cache.clear(), self.key_count.clear())
        wrapper.cache_info = (
            lambda: f"Cache size: {len(self.cache)}, Max size: {self.maxsize}"
        )

        return wrapper


# Erzeugen von Cache-Instanzen für verschiedene Zwecke
string_cache = DynamicLRUCache(initial_size=2048, max_size=10000)
metadata_cache = DynamicLRUCache(initial_size=512, max_size=2000)
lfu_cache = LFUCache(maxsize=2048)


def similarity(a: str, b: str) -> float:
    """Return a similarity ratio between two strings."""
    return SequenceMatcher(
        None, sanitize_filename(a).lower().strip(), sanitize_filename(b).lower().strip()
    ).ratio()


# Verbesserungsvorschlag #1 und #7: Optimierte Dateinamenbereinigung mit dynamischem Caching
@string_cache.decorator
def sanitize_filename(filename: Optional[Any]) -> str:
    """Bereinigt Dateinamen mit Unicode-Normalisierung und Ersetzung unerwünschter Zeichen"""
    try:
        if filename is None:
            return ""

        # Sicherstellen, dass es ein String ist
        filename = str(filename)

        # Early check für max length - Verbesserungsvorschlag #7.1
        if len(filename) > Config.MAX_FILENAME_LENGTH:
            filename = filename[: Config.MAX_FILENAME_LENGTH]

        # Unicode Normalization
        filename = unicodedata.normalize("NFC", filename)

        # Ersetze verbotene Zeichen mit vorcompilierten Patterns - Verbesserungsvorschlag #4
        filename = ILLEGAL_CHARS_PATTERN.sub(" ", filename)

        # Behalte "feat."-Notation bei
        filename = FEAT_NOTATION_PATTERN.sub(" feat. \\1", filename)

        # Bereinige überflüssige Leerzeichen
        filename = EXTRA_SPACES_PATTERN.sub(" ", filename).strip()

        return filename

    except Exception as e:
        log_error(
            f"Dateinamen-Bereinigung fehlgeschlagen: {str(e)}",
            {"filename": str(filename)},
        )
        return "ungueltiger_dateiname"


# ---------------------------
# I/O-Operationen mit Semaphore und besserer Parallelisierung
# ---------------------------

# Globaler Semaphor für I/O-Operationen - Verbesserungsvorschlag #2
# Begrenzt die Anzahl gleichzeitiger I/O-Operationen
IO_SEMAPHORE = asyncio.Semaphore(20)  # Anpassbar je nach System

# I/O Operation Buffer - Verbesserungsvorschlag #3
IO_BUFFER = {}
IO_BUFFER_LOCK = asyncio.Lock()
IO_BUFFER_MAX_SIZE = 100


async def buffer_operation(key: str, operation: Callable, *args, **kwargs) -> Any:
    """Puffert I/O-Operationen und führt sie in Batches aus"""
    async with IO_BUFFER_LOCK:
        if key not in IO_BUFFER:
            IO_BUFFER[key] = []
        IO_BUFFER[key].append((operation, args, kwargs))

        # Wenn der Puffer voll ist oder dieser Schlüssel bereits viele Einträge hat,
        # führe die Operationen aus
        if len(IO_BUFFER) > IO_BUFFER_MAX_SIZE or len(IO_BUFFER[key]) > 10:
            return await flush_buffer(key)

    # Kein sofortiges Ausführen nötig
    return None


async def flush_buffer(key: Optional[str] = None) -> Any:
    """Führt gepufferte Operationen aus"""
    result = None
    async with IO_BUFFER_LOCK:
        if key is not None and key in IO_BUFFER:
            operations = IO_BUFFER.pop(key)
            for op, args, kwargs in operations:
                # Die letzte Operation bestimmt das Ergebnis
                result = await op(*args, **kwargs)
        elif key is None:
            # Alle Operationen ausführen
            all_keys = list(IO_BUFFER.keys())
            for k in all_keys:
                operations = IO_BUFFER.pop(k)
                for op, args, kwargs in operations:
                    await op(*args, **kwargs)
    return result


# Implementierung von Verbesserungsvorschlag #3: Plattformspezifisches, atomisches Umbenennen
async def atomic_rename(src: Union[str, Path], dest: Union[str, Path]) -> bool:
    """Führt ein atomisches Umbenennen durch, falls vom Betriebssystem unterstützt"""
    src_path = Path(src)
    dest_path = Path(dest)

    # Sicherstellen, dass das Zielverzeichnis existiert
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if os.name == "posix":
            # Auf POSIX-Systemen ist os.rename atomar
            os.rename(str(src_path), str(dest_path))
        else:
            # Auf Windows versuchen wir es mit shutil.move
            shutil.move(str(src_path), str(dest_path))
        return True
    except Exception as e:
        logger.error(f"Atomisches Umbenennen fehlgeschlagen: {e}")
        return False


async def safe_rename(
    src: Union[str, Path], dest: Union[str, Path], max_retries: int = 3
) -> bool:
    """Robustes Umbenennen mit Wiederholungslogik und Semaphor für begrenzte Parallelität"""
    src_path = Path(src)
    dest_path = Path(dest)

    if not src_path.exists():
        return False

    # Verbesserungsvorschlag #2: Semaphore für begrenzte Parallelität
    async with IO_SEMAPHORE:
        # Versuche zuerst atomisches Umbenennen
        if await atomic_rename(src_path, dest_path):
            return True

        # Fallback: Mit Wiederholungen
        for attempt in range(max_retries):
            try:
                os.rename(str(src_path), str(dest_path))
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Umbenennen fehlgeschlagen nach {max_retries} Versuchen: {e}"
                    )
                    raise
                await asyncio.sleep(1)
        return False


# Verbesserungsvorschlag #2: Chunking für Batch-Verarbeitung großer Listen
async def batch_rename(
    src_dest_pairs: List[Tuple[Union[str, Path], Union[str, Path]]],
    chunk_size: int = 50,
) -> List[bool]:
    """Verarbeitet mehrere Umbenennungsoperationen in Chunks"""
    results = []

    # Verarbeite die Liste in Chunks
    for i in range(0, len(src_dest_pairs), chunk_size):
        chunk = src_dest_pairs[i : i + chunk_size]
        # Erstelle Tasks für diesen Chunk
        tasks = [safe_rename(src, dest) for src, dest in chunk]
        # Führe die Tasks parallel aus
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
        # Wandle Exceptions in False um
        processed_results = [
            result if not isinstance(result, Exception) else False
            for result in chunk_results
        ]
        results.extend(processed_results)

        # Kurze Pause zwischen Chunks
        if i + chunk_size < len(src_dest_pairs):
            await asyncio.sleep(0.1)

    return results


# Datei-Cache für häufig verwendete Dateien - Verbesserungsvorschlag #3
FILE_CACHE = {}
FILE_CACHE_MAX_SIZE = 50  # MB
FILE_CACHE_CURRENT_SIZE = 0
FILE_CACHE_LOCK = asyncio.Lock()


async def cache_file(filepath: Union[str, Path]) -> bool:
    """Lädt eine Datei in den Cache"""
    path = Path(filepath)
    global FILE_CACHE_CURRENT_SIZE

    if not path.exists():
        return False

    try:
        size_mb = path.stat().st_size / (1024 * 1024)

        # Prüfe, ob die Datei in den Cache passt
        if (
            size_mb > FILE_CACHE_MAX_SIZE * 0.5
        ):  # Einzelne Datei darf max. 50% des Caches belegen
            return False

        async with FILE_CACHE_LOCK:
            # Cache aufräumen, wenn er zu groß wird
            if FILE_CACHE_CURRENT_SIZE + size_mb > FILE_CACHE_MAX_SIZE:
                # Entferne die ältesten Einträge
                while (
                    FILE_CACHE
                    and FILE_CACHE_CURRENT_SIZE + size_mb > FILE_CACHE_MAX_SIZE * 0.8
                ):
                    _, oldest_size = FILE_CACHE.popitem()
                    FILE_CACHE_CURRENT_SIZE -= oldest_size

            # Datei in den Cache laden
            with open(path, "rb") as f:
                content = f.read()
                FILE_CACHE[str(path)] = (content, size_mb)
                FILE_CACHE_CURRENT_SIZE += size_mb

        return True
    except Exception as e:
        logger.error(f"Fehler beim Cachen von {path}: {e}")
        return False


async def verify_file(
    filepath: Union[str, Path], max_attempts: int = 10, delay: int = 1
) -> bool:
    """Überprüft asynchron die Existenz und Integrität einer Datei mit Cache-Unterstützung"""
    path = Path(filepath)

    # Prüfe zuerst den Cache
    if str(path) in FILE_CACHE:
        return True

    # Verbesserungsvorschlag #2: Semaphore für begrenzte Parallelität
    async with IO_SEMAPHORE:
        for _ in range(max_attempts):
            if path.exists() and path.stat().st_size > 0:
                # Ggf. Datei cachen für zukünftige Zugriffe
                if path.stat().st_size < 10 * 1024 * 1024:  # Nur Dateien < 10MB cachen
                    await cache_file(path)
                return True
            await asyncio.sleep(delay)
        return False


# ---------------------------
# Musik-spezifische Hilfsfunktionen
# ---------------------------


# Verbesserte Version des Dictionaries für hashbaren Zugriff
class HashableDict(dict):
    def __hash__(self):
        return hash(tuple(sorted(self.items())))


def make_hashable(obj: Any) -> Any:
    """Konvertiert unhashbare Python-Objekte in hashbare Äquivalente"""
    if isinstance(obj, dict):
        return frozenset((k, make_hashable(v)) for k, v in obj.items())
    elif isinstance(obj, list):
        return tuple(make_hashable(i) for i in obj)
    elif isinstance(obj, set):
        return frozenset(make_hashable(i) for i in obj)
    else:
        return obj


# Implementierung eines verbesserten dict-sicheren lru_cache
def dict_safe_lru_cache(maxsize=128, typed=False):
    """Eine verbesserte Variante von lru_cache, die mit Dictionaries umgehen kann."""

    def decorator(func):
        cache = {}
        stats = {"hits": 0, "misses": 0}
        sentinel = object()  # Zum Prüfen auf Cache-Misses

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Erstelle hashbaren Schlüssel mit optimierter Hashfunktion
            hashable_args = tuple(make_hashable(arg) for arg in args)
            hashable_kwargs = frozenset(
                (k, make_hashable(v)) for k, v in kwargs.items()
            )
            key = hash((hashable_args, hashable_kwargs, func.__name__))

            # Cache-Lookup
            result = cache.get(key, sentinel)
            if result is not sentinel:
                stats["hits"] += 1
                return result

            # Cache-Miss: Führe die Funktion aus
            stats["misses"] += 1
            result = func(*args, **kwargs)

            # Cache aktualisieren
            if len(cache) >= maxsize:
                # LRU-Strategie: Entferne einen zufälligen Eintrag
                # (echtes LRU ist komplex ohne OrderedDict)
                try:
                    cache.pop(next(iter(cache)))
                except:
                    cache.clear()  # Fallback: Cache leeren

            cache[key] = result
            return result

        # API-Kompatibilität mit functools.lru_cache
        wrapper.cache_info = (
            lambda: f"CacheInfo(hits={stats['hits']}, misses={stats['misses']}, maxsize={maxsize}, currsize={len(cache)})"
        )
        wrapper.cache_clear = lambda: cache.clear()

        return wrapper

    return decorator


@string_cache.decorator
def fix_artist_from_title_if_needed(artist: str, title: str) -> str:
    """Extrahiert den Artist aus dem Titel, wenn nötig"""
    from config import Config

    # Implementierung von Verbesserungsvorschlag #6: Lokale Zwischenspeicherung
    bad_artists = getattr(Config, "_bad_artists_cache", None)
    if bad_artists is None:
        bad_artists = frozenset(
            a.lower()
            for a in Config.ORGANIZER_CONFIG.get("replace_artist_from_title_if", [])
        )
        # Cache im Config-Objekt speichern
        setattr(Config, "_bad_artists_cache", bad_artists)

    if not artist or not title:
        return artist

    if artist.lower() not in bad_artists:
        return artist

    # Optimiertes Pattern-Matching mit kompiliertem Pattern
    ARTIST_TITLE_PATTERN = getattr(fix_artist_from_title_if_needed, "_pattern", None)
    if ARTIST_TITLE_PATTERN is None:
        ARTIST_TITLE_PATTERN = re.compile(r"(?P<artist>.+?)\s*[-–]\s*(?P<title>.+)")
        setattr(fix_artist_from_title_if_needed, "_pattern", ARTIST_TITLE_PATTERN)

    match = ARTIST_TITLE_PATTERN.match(title)
    if match:
        extracted = match.group("artist").strip()
        if (
            extracted and len(extracted) < 40
        ):  # Maximal 40 Zeichen für einen sinnvollen Künstlernamen
            return extracted

    return artist


@string_cache.decorator
def extract_featured_artist(title: str) -> Tuple[str, Optional[str]]:
    """Erkennt Featured Artists in verschiedenen Schreibweisen mit Early-Return"""
    # Implementierung von Verbesserungsvorschlag #7: Early-return nach erstem Match
    if not title or len(title) < 5:  # Kurze Strings überspringen
        return title, None

    # Verwende die vorcompilierten Patterns
    for pattern in FEAT_PATTERNS:
        match = pattern.search(title)
        if match:
            group = match.group(2) if len(match.groups()) > 1 else match.group(1)
            # String-Builder Pattern: Nutze replace statt sub für bessere Performance
            clean_title = title[: match.start()] + title[match.end() :]
            clean_title = clean_title.strip()
            return clean_title, group.strip()

    # Kein Match gefunden
    return title, None


@string_cache.decorator
def clean_artist_name(artist_string: str) -> str:
    """Reinigt und normalisiert Artistnamen, behält nur den ersten und entfernt Titelanhänge."""
    if not artist_string:
        return "Various Artists"

    # Schritt 1: Nur den Teil vor einem Titel-Trenner wie " - ", "–", "—"
    artist_string = re.split(r"\s*[-–—]\s*", artist_string)[0]

    # Schritt 2: Trennen bei typischen Multi-Artist-Konstruktionen und ersten Eintrag nehmen
    artist_string = re.split(r",|&|feat\.|ft\.|with", artist_string, flags=re.IGNORECASE)[0]

    # Schritt 3: Anwenden des vorcompilierten Cleanups (wie bisher)
    artist = ARTIST_CLEANUP_PATTERN.sub("", artist_string)

    # Schritt 4: Finales Säubern
    return sanitize_filename(artist).strip() or "Various Artists"


@string_cache.decorator
def extract_main_artist(artist: str) -> str:
    """Extrahiert den Hauptkünstler aus einem String"""
    from config import ARTIST_NAME_OVERRIDES

    # Lokale Zwischenspeicherung von häufig verwendeten Werten - Verbesserungsvorschlag #6
    overrides_lowercase = getattr(extract_main_artist, "_overrides_lowercase", None)
    if overrides_lowercase is None:
        overrides_lowercase = {k.lower(): v for k, v in ARTIST_NAME_OVERRIDES.items()}
        setattr(extract_main_artist, "_overrides_lowercase", overrides_lowercase)

    # String-Builder Pattern: Nutze split mit maxsplit=1 direkt
    raw = ARTIST_SPLIT_PATTERN.split(artist, maxsplit=1)[0].strip()

    # Optimierter Lookup mit vorberechneten Lowercase-Keys
    return overrides_lowercase.get(raw.lower(), raw)


@lfu_cache.decorator
def identify_album_from_video(info: Dict[str, Any]) -> Optional[str]:
    """
    Versucht, den Albumnamen aus den Videoinformationen zu extrahieren mit LFU Cache.
    """
    # Verbesserungsvorschlag #6: Reduzierte String-Operationen
    info_title = info.get("title", "")
    info_description = info.get("description", "")

    # Early-Return für leere Strings
    if not info_title and not info_description:
        return None

    possible_fields = [info_title, info_description]

    # Verwende vorkompilierte Patterns
    for field in possible_fields:
        for pattern in ALBUM_PATTERNS:
            match = pattern.search(field)
            if match:
                return sanitize_filename(match.group(1).strip())

    return None


# ---------------------------
# MetadataManager Wrapper mit verbesserten Cache-Strategien
# ---------------------------

from metadata import process_metadata, write_metadata


class MetadataManager:
    # Statische Cache für häufig verwendete Metadaten - Verbesserungsvorschlag #6
    _metadata_cache = {}
    _cache_hits = 0
    _cache_misses = 0
    _cache_lock = asyncio.Lock()
    _MAX_CACHE_SIZE = 500

    @staticmethod
    def clean_title(title: str, artist: str) -> str:
        """
        Entfernt den Artist aus dem Titel, wenn er doppelt vorkommt (z. B. 'Kygo, HAYLA - Without You')
        oder ähnliche Konstellationen wie 'Artist - Title (Remix)'.

        Args:
            title (str): Der ursprüngliche Titel (z. B. 'Kygo, HAYLA - Without You (Remix)')
            artist (str): Der vollständige Artist (z. B. 'Kygo, HAYLA')

        Returns:
            str: Bereinigter Titel (z. B. 'Without You')
        """
        if not title or not artist:
            return title

        original_title = title  # Zurückbehalten für Log oder Fallback

        # 1. Klammerzusätze wie (Remix), (Official Video) etc. entfernen
        title = re.sub(r"\s*\(.*?\)", "", title).strip()

        title_lower = title.lower()
        artist_lower = artist.lower().strip()

        # 2. Direktes Entfernen, wenn der Titel mit dem vollständigen Artist beginnt
        if title_lower.startswith(artist_lower + ' - '):
            return title[len(artist) + 3:].strip()

        # 3. Entferne alle Teile, die dem Artist entsprechen (z. B. 'Kygo, HAYLA' → 'Without You')
        title_parts = title.split(' - ')
        artist_parts = [part.strip().lower() for part in re.split(r",|&|feat\.|ft\.|with", artist_lower)]

        cleaned_parts = []
        for part in title_parts:
            if not any(artist in part.lower() for artist in artist_parts):
                cleaned_parts.append(part.strip())

        cleaned_title = " - ".join(cleaned_parts).strip()

        return cleaned_title or original_title.strip()

    @staticmethod
    def escape_markdown_v2(text: str) -> str:
        """Escaped spezielle Zeichen für Telegram MarkdownV2"""
        if not text:
            return ""
        text = str(text)
        reserved_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in reserved_chars:
            text = text.replace(char, f'\\{char}')
        return text

    @classmethod
    async def get_cache_stats(cls):
        """Gibt Cache-Statistiken zurück"""
        return {
            "size": len(cls._metadata_cache),
            "max_size": cls._MAX_CACHE_SIZE,
            "hits": cls._cache_hits,
            "misses": cls._cache_misses,
            "hit_ratio": (
                cls._cache_hits / (cls._cache_hits + cls._cache_misses)
                if (cls._cache_hits + cls._cache_misses) > 0
                else 0
            ),
        }

    @staticmethod
    async def process(info: dict) -> dict:
        return await process_metadata(info)

    @staticmethod
    async def write(src_path: str, metadata: dict, dest_path: str):
        await write_metadata(src_path, metadata, dest_path)

    @classmethod
    async def enrich_metadata(cls, info: dict) -> dict:
        """Verbesserte enrich_metadata mit intelligentem Caching und LFU-Strategie"""
        # Erstelle einen hashbaren Schlüssel für das Dictionary
        cache_key = make_hashable(info)

        # Prüfe zuerst den Cache
        async with cls._cache_lock:
            if cache_key in cls._metadata_cache:
                cls._cache_hits += 1
                return cls._metadata_cache[cache_key]
            cls._cache_misses += 1

        # Cache Miss: Führe die Verarbeitung durch
        result = await cls.process(info)

        # Aktualisiere den Cache mit LFU-Strategie
        async with cls._cache_lock:
            # Cache-Bereinigung, wenn Maximalgröße erreicht ist
            if len(cls._metadata_cache) >= cls._MAX_CACHE_SIZE:
                # Entferne 10% der am wenigsten verwendeten Einträge
                items_to_remove = int(cls._MAX_CACHE_SIZE * 0.1)
                if items_to_remove > 0:
                    for _ in range(items_to_remove):
                        if cls._metadata_cache:
                            cls._metadata_cache.pop(next(iter(cls._metadata_cache)))

            # Füge neuen Eintrag hinzu
            cls._metadata_cache[cache_key] = result

        return result

    @classmethod
    async def batch_process(cls, info_list: List[dict]) -> List[dict]:
        """Verarbeitet mehrere Metadaten-Dictionaries parallel"""
        # Verbesserungsvorschlag #2: Chunking für große Listen
        chunk_size = 20
        results = []

        for i in range(0, len(info_list), chunk_size):
            chunk = info_list[i : i + chunk_size]
            tasks = [cls.enrich_metadata(info) for info in chunk]
            chunk_results = await asyncio.gather(*tasks)
            results.extend(chunk_results)

            # Kurze Pause zwischen Chunks
            if i + chunk_size < len(info_list):
                await asyncio.sleep(0.1)

        return results

    @classmethod
    async def batch_write(cls, operations: List[Tuple[str, dict, str]]) -> List[bool]:
        """Schreibt mehrere Metadaten parallel"""
        # Verbesserungsvorschlag #4: Batch-Schreiben von Metadaten
        chunk_size = 10
        results = []

        for i in range(0, len(operations), chunk_size):
            chunk = operations[i : i + chunk_size]
            tasks = [write_metadata(src, meta, dest) for src, meta, dest in chunk]
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Wandle Exceptions in False um
            processed_results = [
                True if not isinstance(result, Exception) else False
                for result in chunk_results
            ]
            results.extend(processed_results)

            # Kurze Pause zwischen Chunks
            if i + chunk_size < len(operations):
                await asyncio.sleep(0.1)

        return results


# ---------------------------
# Metadata Handling
# ---------------------------


# Verbesserungsvorschlag #5: Typisierte Metadaten und Freezable Dataclass
@dataclass(frozen=True)
class AudioMetadata:
    """Unveränderliche Metadaten-Klasse für Audio-Dateien"""

    title: str
    artist: str
    album: str = field(default="Unknown Album")
    album_artist: Optional[str] = None
    year: str = field(default_factory=lambda: str(datetime.now().year))
    genre: str = "Unknown"
    track_number: int = 1
    thumbnail: Optional[str] = None

    def __post_init__(self):
        """Stellt sicher, dass alle String-Felder sanitär sind"""
        # Da die Klasse frozen ist, müssen wir den __setattr__ von object überschreiben
        object.__setattr__(self, "title", sanitize_filename(self.title))
        object.__setattr__(self, "artist", sanitize_filename(self.artist))
        object.__setattr__(self, "album", sanitize_filename(self.album))
        if self.album_artist:
            object.__setattr__(
                self, "album_artist", sanitize_filename(self.album_artist)
            )
        else:
            object.__setattr__(self, "album_artist", self.artist)


# Thumbnail Caching für write_metadata - Verbesserungsvorschlag #4
THUMBNAIL_CACHE = {}
THUMBNAIL_CACHE_MAX_SIZE = 20 * 1024 * 1024  # 20 MB
THUMBNAIL_CACHE_CURRENT_SIZE = 0
THUMBNAIL_CACHE_LOCK = asyncio.Lock()


async def cache_thumbnail(url: str) -> Optional[bytes]:
    """Lädt ein Thumbnail und cached es"""
    global THUMBNAIL_CACHE_CURRENT_SIZE

    # Prüfe zuerst den Cache
    if url in THUMBNAIL_CACHE:
        return THUMBNAIL_CACHE[url]

    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    content = await response.read()

                    # Cache das Thumbnail
                    async with THUMBNAIL_CACHE_LOCK:
                        # Cache bereinigen, wenn er zu groß wird
                        if (
                            THUMBNAIL_CACHE_CURRENT_SIZE + len(content)
                            > THUMBNAIL_CACHE_MAX_SIZE
                        ):
                            # Entferne älteste Einträge
                            while (
                                THUMBNAIL_CACHE
                                and THUMBNAIL_CACHE_CURRENT_SIZE + len(content)
                                > THUMBNAIL_CACHE_MAX_SIZE * 0.8
                            ):
                                _, oldest_content = THUMBNAIL_CACHE.popitem()
                                THUMBNAIL_CACHE_CURRENT_SIZE -= len(oldest_content)

                        # Neues Thumbnail cachen
                        THUMBNAIL_CACHE[url] = content
                        THUMBNAIL_CACHE_CURRENT_SIZE += len(content)

                    return content
    except Exception as e:
        logger.error(f"Thumbnail-Cache-Fehler: {e}")

    return None


async def write_metadata_to_thread(
    src_path: Union[str, Path], metadata: Dict[str, Any], dest_path: Union[str, Path]
) -> bool:
    """
    Führt CPU-intensive Metadaten-Schreiboperationen in einem separaten Thread aus
    Verbesserungsvorschlag #2: asyncio.to_thread für CPU-intensive Operationen
    """
    loop = asyncio.get_event_loop()

    # Definiere die CPU-intensive Operation
    def write_metadata_sync():
        try:
            src_str = str(src_path)
            dest_str = str(dest_path)

            # Verbesserungsvorschlag #5: Lokale Config-Zwischenspeicherung
            default_album = getattr(Config, "_default_album_cache", None)
            if default_album is None:
                default_album = Config.DEFAULT_ALBUM_NAME
                setattr(Config, "_default_album_cache", default_album)

            metadata_defaults = getattr(Config, "_metadata_defaults_cache", None)
            if metadata_defaults is None:
                metadata_defaults = Config.METADATA_DEFAULTS
                setattr(Config, "_metadata_defaults_cache", metadata_defaults)

            audio = MP4(src_str)

            # Standard-Metadaten
            audio["\xa9nam"] = metadata["title"]
            audio["\xa9ART"] = metadata["artist"]
            audio["\xa9alb"] = metadata.get("album", default_album)
            audio["aART"] = metadata.get("album_artist", metadata["artist"])
            audio["\xa9day"] = str(metadata.get("year", datetime.now().year))
            audio["\xa9gen"] = metadata.get("genre", metadata_defaults["genre"])
            audio["trkn"] = [(metadata.get("track_number", 1), 0)]

            # Cover Art aus dem Cache
            if "thumbnail" in metadata and "thumbnail_data" in metadata:
                audio["covr"] = [
                    MP4Cover(
                        metadata["thumbnail_data"], imageformat=MP4Cover.FORMAT_JPEG
                    )
                ]

            audio.save()
            return True
        except Exception as e:
            logger.error(f"Fehler beim Schreiben der Metadaten: {e}")
            return False

    # Führe die Operation in einem Thread aus
    try:
        return await loop.run_in_executor(None, write_metadata_sync)
    except Exception as e:
        logger.error(f"Thread-Ausführungsfehler: {e}")
        return False


async def write_metadata(
    src_path: Union[str, Path], metadata: Dict[str, Any], dest_path: Union[str, Path]
) -> None:
    """Schreibt Metadaten in eine Audiodatei mit Thumbnail Caching"""
    src_str = str(src_path)
    dest_str = str(dest_path)

    # Verbesserungsvorschlag #5: Lokale Config-Zwischenspeicherung
    default_album = Config.DEFAULT_ALBUM_NAME
    metadata_defaults = Config.METADATA_DEFAULTS

    # Thumbnail im Voraus laden und cachen, falls vorhanden
    if "thumbnail" in metadata and isinstance(metadata["thumbnail"], str):
        thumbnail_data = await cache_thumbnail(metadata["thumbnail"])
        if thumbnail_data:
            metadata["thumbnail_data"] = thumbnail_data

    try:
        # Verwende Threading für die CPU-intensive Operation
        success = await write_metadata_to_thread(src_str, metadata, dest_str)

        if success:
            # Wenn Metadaten erfolgreich geschrieben wurden, führe das Umbenennen durch
            await safe_rename(src_str, dest_str)
        else:
            raise Exception("Metadatenschreiben fehlgeschlagen")

    # Verbesserungsvorschlag #7: Spezifische Exception-Typen
    except MutagenError as e:
        log_error(f"Mutagen-Fehler: {str(e)}", {"file": src_str})
        raise
    except IOError as e:
        log_error(f"IO-Fehler beim Metadatenschreiben: {str(e)}", {"file": src_str})
        raise
    except Exception as e:
        log_error(f"Unerwarteter Fehler: {str(e)}", {"file": src_str})
        raise


# ---------------------------
# File Organizer
# ---------------------------


# Implementierung von Verbesserungsvorschlag #9: Typisierte Datenstrukturen
@dataclass
class FileMetadata:
    artist: str
    title: str
    album: str
    year: str
    track: int
    album_artist: Optional[str] = None
    is_single: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileMetadata":
        """Erstellt eine FileMetadata-Instanz aus einem Dictionary"""
        return cls(
            artist=data.get("artist", "Unknown Artist"),
            title=data.get("title", "Unknown Title"),
            album=data.get("album", "Unknown Album"),
            year=data.get("year", str(datetime.now().year)),
            track=int(data.get("track", 1)),
            album_artist=data.get("album_artist"),
            is_single=data.get("is_single", False),
        )


class FilenameFixerTool:
    # Verbesserungsvorschlag #8: Statische Variablen
    _DEFAULT_YEAR = str(datetime.now().year)
    _VALID_EXTENSIONS = frozenset([".m4a", ".mp3", ".flac"])
    _BATCH_SIZE = 50

    def __init__(
        self,
        source_dir: Optional[str] = None,
        library_dir: Optional[str] = None,
        fail_dir: Optional[str] = None,
    ):
        # Config-Werte zwischenspeichern - Verbesserungsvorschlag #6
        source_default = getattr(Config, "PROCESSED_DIR", "./prozess")
        library_default = getattr(Config, "LIBRARY_DIR", "./library")
        fail_default = getattr(Config, "FAIL_DIR", "./failed")

        self.source_dir = Path(source_dir if source_dir else source_default)
        self.library_dir = Path(library_dir if library_dir else library_default)
        self.fail_dir = Path(fail_dir if fail_dir else fail_default)
        self.fail_dir.mkdir(exist_ok=True, parents=True)

        # Datenstrukturen für Album-Jahre
        self.album_year_map = {}
        self.temp_year_storage = {}

        # Statistiken
        self.stats = {
            "processed": 0,
            "fixed": 0,
            "moved_to_fail": 0,
            "skipped": 0,
            "start_time": time.time(),
        }

        # Implementierung von Verbesserungsvorschlag #5: Memoization für Config-Zugriffe
        self.organizer_config = Config.ORGANIZER_CONFIG
        self.default_year = getattr(
            Config, "DEFAULT_YEAR", FilenameFixerTool._DEFAULT_YEAR
        )

        # Semaphore für begrenzte Parallelität - Verbesserungsvorschlag #2
        self.concurrency_limit = asyncio.Semaphore(30)

    async def _get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """CPU-intensive Metadaten-Extraktion in separatem Thread"""
        loop = asyncio.get_event_loop()

        try:
            # Führe die Metadaten-Extraktion in einem Thread aus
            return await loop.run_in_executor(
                None, self._extract_metadata_sync, file_path
            )
        except Exception as e:
            logger.error(f"Fehler bei der Metadatenextraktion: {e}")
            return {}

    def _extract_metadata_sync(self, file_path: Path) -> Dict[str, Any]:
        """Synchrone Metadaten-Extraktion für Threading"""
        try:
            metadata = mutagen.File(file_path)
            if not metadata:
                return {}

            result: Dict[str, Any] = {}

            # Verbesserungsvorschlag #5: Lokale Zwischenspeicherung der Tag-Mappings
            if isinstance(metadata, MP4):
                tags = {
                    "artist": "\xa9ART",
                    "album_artist": "aART",
                    "title": "\xa9nam",
                    "album": "\xa9alb",
                    "year": "\xa9day",
                    "track": "trkn",
                }
            else:
                tags = {
                    "artist": "artist",
                    "album_artist": "albumartist",
                    "title": "title",
                    "album": "album",
                    "year": "date",
                    "track": "tracknumber",
                }

            for key, tag in tags.items():
                try:
                    value = metadata[tag][0] if tag in metadata else None
                    result[key] = str(value) if value else None
                except:
                    result[key] = None

            # Verbesserungsvorschlag #5: Lokale Konstanten
            unknown_artist = "Unknown Artist"
            singles_album = "Singles"

            defaults = {
                "artist": unknown_artist,
                "album_artist": result.get("artist"),
                "title": file_path.stem,
                "album": singles_album,
                "year": self.default_year,
                "track": 1,
            }

            for key in defaults:
                result[key] = result.get(key) or defaults[key]

            first_artist = extract_main_artist(result["artist"])
            album = sanitize_filename(result["album"])
            album_key = f"{first_artist}::{album}"

            year_raw = result.get("year")
            try:
                year = int(year_raw)
            except (TypeError, ValueError):
                year = datetime.now().year

            if album_key not in self.temp_year_storage:
                self.temp_year_storage[album_key] = []

            self.temp_year_storage[album_key].append(year)

            # Verbesserungsvorschlag #4: Optimierung der Regex-Nutzung
            try:
                track_raw = (
                    metadata.get("trkn")
                    if isinstance(metadata, MP4)
                    else result["track"]
                )

                if isinstance(track_raw, list) and isinstance(track_raw[0], tuple):
                    result["track"] = track_raw[0][0]
                elif isinstance(track_raw, tuple):
                    result["track"] = track_raw[0]
                else:
                    # Verwende das kompilierte Pattern für bessere Performance
                    track_match = TRACK_NUMBER_PATTERN.search(str(track_raw))
                    result["track"] = int(track_match.group(1)) if track_match else 1
            except:
                result["track"] = 1

            return result

        # Verbesserungsvorschlag #7: Spezifische Exception-Typen
        except MutagenError as e:
            log_error(
                f"Metadaten-Extraktionsfehler (Mutagen): {e}", {"file": str(file_path)}
            )
            return {}
        except (KeyError, ValueError) as e:
            log_error(f"Fehlerhafte Metadaten: {e}", {"file": str(file_path)})
            return {}
        except Exception as e:
            log_error(
                f"Unerwarteter Fehler bei Metadaten: {e}", {"file": str(file_path)}
            )
            return {}

    # Implementierung von Verbesserungsvorschlag #4: Batch-Verarbeitung für Metadaten
    async def _get_batch_metadata(
        self, file_paths: List[Path]
    ) -> Dict[Path, Dict[str, Any]]:
        """Extrahiert Metadaten von mehreren Dateien gleichzeitig mit Chunking"""
        # Verbesserungsvorschlag #2: Chunking für große Listen
        chunk_size = 30
        results = {}

        for i in range(0, len(file_paths), chunk_size):
            chunk = file_paths[i : i + chunk_size]

            # Verbesserungsvorschlag #2: Semaphore für begrenzte Parallelität
            async with self.concurrency_limit:
                tasks = [self._get_metadata(fp) for fp in chunk]
                chunk_results = await asyncio.gather(*tasks)

                # Ergebnisse zum Dictionary hinzufügen
                for fp, meta in zip(chunk, chunk_results):
                    results[fp] = meta

            # Kurze Pause zwischen Chunks
            if i + chunk_size < len(file_paths):
                await asyncio.sleep(0.1)

        return results

    async def _move_to_fail(self, file_path: Path, reason: str) -> None:
        """Verschiebt fehlerhafte Dateien in den Fehlerordner"""
        try:
            self.stats["moved_to_fail"] += 1
            # Beschränke die Länge des Grundes
            reason_part = re.sub(r"[^\w\s-]", "_", reason[:20])
            new_name = f"{file_path.stem}_ERROR_{reason_part}{file_path.suffix}"
            target = self.fail_dir / new_name
            counter = 1

            # Finde einen eindeutigen Dateinamen
            while target.exists():
                target = (
                    self.fail_dir
                    / f"{file_path.stem}_ERROR_{reason_part}_{counter}{file_path.suffix}"
                )
                counter += 1

            await safe_rename(file_path, target)

        except Exception as e:
            log_error(f"Critical move error: {e}", {"file": str(file_path)})

    async def fix_file(self, file_path: Path) -> bool:
        """Korrigiert eine einzelne Datei mit Optimierungen"""
        try:
            # Verbesserungsvorschlag #10: Logging statt Prints
            logger.debug(f"Starte fix_file für: {file_path}")
            self.stats["processed"] += 1

            # Early-Return für ungültige Dateiendungen - Verbesserungsvorschlag #7
            if file_path.suffix.lower() not in FilenameFixerTool._VALID_EXTENSIONS:
                logger.debug("Ungültige Dateiendung – wird übersprungen.")
                self.stats["skipped"] += 1
                return False

            # Prüfe ob die Datei existiert und nicht leer ist
            if not await verify_file(file_path):
                logger.debug(
                    "Datei existiert nicht oder ist leer – verschiebe zu failed."
                )
                await self._move_to_fail(file_path, "Invalid file")
                return False

            # Metadaten abrufen
            metadata = await self._get_metadata(file_path)
            logger.debug(f"Extrahierte Metadaten: {metadata}")

            if not metadata:
                logger.debug("Keine Metadaten – verschiebe zu failed.")
                await self._move_to_fail(file_path, "No metadata")
                return False

            # Implementierung von Verbesserungsvorschlag #8: Vermeidung redundanter Berechnungen
            artist_raw = metadata.get("artist", "Unknown Artist")
            title_raw = metadata.get("title", file_path.stem)

            # Künstler aus Titel extrahieren, falls nötig
            artist_corrected = fix_artist_from_title_if_needed(artist_raw, title_raw)

            # Implementierung von Verbesserungsvorschlag #6: Reduzierte String-Operationen
            # Einmalige Berechnung von sanitize_filename für artist_corrected
            sanitized_artist_corrected = sanitize_filename(artist_corrected.strip())

            # Künstlernamen-Overrides verwenden
            artist = ARTIST_NAME_OVERRIDES.get(
                artist_corrected.strip(), sanitized_artist_corrected
            )

            # Einmalige Berechnung von sanitize_filename für album
            album = sanitize_filename(metadata.get("album", "Unknown Album"))

            # Track-Nummer extrahieren
            track_raw = metadata.get("track", 1)
            try:
                # Implementierung der konsistenten Regex-Nutzung (Verbesserungsvorschlag #4)
                track_match = TRACK_NUMBER_PATTERN.search(str(track_raw))
                track = int(track_match.group(1)) if track_match else 1
            except Exception:
                track = 1
            
            # Hauptkünstler extrahieren
            artist = extract_main_artist(artist)
            
            # Titel bereinigen (NEU & VERBESSERT)
            # Wir nutzen deine bestehende Funktion aus dem MetadataManager.
            title_cleaned = MetadataManager.clean_title(title_raw, artist)
            
            # Regelbasierte Titelkorrektur (dieser Teil bleibt wie er ist)
            rules = self.organizer_config.get("filename_rules", {})
            for pattern, repl in rules.items():
                title_cleaned = re.sub(
                    pattern, repl, title_cleaned, flags=re.IGNORECASE
                )
            
            # Regelbasierte Titelkorrektur
            # Verwendung der zwischengespeicherten Config
            rules = self.organizer_config.get("filename_rules", {})
            for pattern, repl in rules.items():
                title_cleaned = re.sub(
                    pattern, repl, title_cleaned, flags=re.IGNORECASE
                )
            
            # Leerzeichen normalisieren
            title_cleaned = re.sub(r"\s+", " ", title_cleaned).strip()
            title = sanitize_filename(title_cleaned)
            metadata["title"] = title
            extension = file_path.suffix
            
            logger.debug(f"artist_raw: {artist_raw} → {artist}")
            logger.debug(f"title_raw: {title_raw} → {title}")

            # Album-Jahr bestimmen
            album_key = f"{artist}::{album}"
            year = str(self.album_year_map.get(album_key, datetime.now().year))
            metadata["year"] = year
            is_single = metadata.get("is_single", False)

            # Zielverzeichnis und Dateiname bestimmen
            if album.lower() in ["single", "singles"] or is_single:
                target_dir = self.library_dir / artist / "Singles"
                filename = f"{metadata['year']} - {title}{extension}"
            else:
                year_album = f"{metadata['year']} {album}"
                target_dir = self.library_dir / artist / year_album
                filename = f"{track:02d} - {title}{extension}"

            # Verzeichnis erstellen, falls es nicht existiert
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / filename

            # Eindeutigen Dateinamen finden, falls bereits existiert
            if target_path.exists():
                base = target_path.stem
                counter = 1
                while (target_dir / f"{base} ({counter}){extension}").exists():
                    counter += 1
                target_path = target_dir / f"{base} ({counter}){extension}"

            logger.debug(f"Zielpfad: {target_path}")

            # Umbenennen durchführen
            await safe_rename(file_path, target_path)
            self.stats["fixed"] += 1
            return True

        # Verbesserungsvorschlag #7: Spezifische Exception-Typen
        except IOError as e:
            logger.error(f"IO-Fehler in fix_file(): {e}")
            await self._move_to_fail(file_path, f"IOError: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Ausnahme in fix_file(): {e}")
            await self._move_to_fail(file_path, str(e))
            return False

    # Implementierung von Verbesserungsvorschlag #2: Parallelisierung der Dateiverarbeitung mit Chunking
    async def process_directory(self, directory: Optional[Path] = None) -> None:
        """
        Verarbeitet alle Dateien in einem Verzeichnis mit optimierter Parallelität,
        Chunking und besserer Ressourcennutzung
        """
        target_dir = directory or self.source_dir
        start_time = time.time()

        # Alle Dateien sammeln
        files = [f for f in target_dir.glob("*.*") if f.is_file()]
        total_files = len(files)

        if not files:
            logger.info("Keine Dateien zum Verarbeiten gefunden.")
            return

        logger.info(f"{total_files} Dateien gefunden. Starte Verarbeitung...")

        # Metadaten parallel sammeln mit Chunking
        logger.info("Sammle Metadaten...")
        metadata_dict = await self._get_batch_metadata(files)

        # Jahre berechnen
        for key, years in self.temp_year_storage.items():
            # Verwende das früheste Jahr für jedes Album
            valid_years = [
                y
                for y in years
                if isinstance(y, int) and 1900 <= y <= datetime.now().year
            ]
            if valid_years:
                self.album_year_map[key] = str(min(valid_years))
            else:
                self.album_year_map[key] = str(datetime.now().year)

        # Dateien in Chunks verarbeiten für bessere Ressourcennutzung
        logger.info("Verarbeite Dateien in Chunks...")
        chunk_size = FilenameFixerTool._BATCH_SIZE
        for i in range(0, len(files), chunk_size):
            chunk = files[i : i + chunk_size]
            # Verarbeite einen Chunk parallel
            tasks = [self.fix_file(file_path) for file_path in chunk]
            await asyncio.gather(*tasks)

            # Status nach jedem Chunk ausgeben
            processed_so_far = min(i + chunk_size, total_files)
            elapsed = time.time() - start_time
            files_per_second = processed_so_far / elapsed if elapsed > 0 else 0
            logger.info(
                f"Fortschritt: {processed_so_far}/{total_files} ({processed_so_far/total_files*100:.1f}%) - {files_per_second:.1f} Dateien/s"
            )

            # Kurze Pause zwischen Chunks für andere Tasks
            if i + chunk_size < len(files):
                await asyncio.sleep(0.1)

        # Abschließende Statistiken
        end_time = time.time()
        elapsed = end_time - start_time
        logger.info(
            f"""
        Verarbeitung abgeschlossen in {elapsed:.2f} Sekunden.
        Dateien gesamt: {total_files}
        Verarbeitet: {self.stats['processed']}
        Korrigiert: {self.stats['fixed']}
        Übersprungen: {self.stats['skipped']}
        Fehlgeschlagen: {self.stats['moved_to_fail']}
        Durchschnitt: {total_files / elapsed:.2f} Dateien/Sekunde
        """
        )

    # Implementierung von Verbesserungsvorschlag #3: Batch-Verarbeitung für Dateisystemoperationen
    async def batch_process_files(self, files: List[Path]) -> Dict[str, Any]:
        """
        Verarbeitet eine Liste von Dateien in optimierten Batches
        und gibt Statistiken zurück
        """
        if not files:
            return {"processed": 0, "success": 0, "failed": 0}

        # Dateien in Chunks aufteilen
        chunks = [
            files[i : i + FilenameFixerTool._BATCH_SIZE]
            for i in range(0, len(files), FilenameFixerTool._BATCH_SIZE)
        ]
        total_stats = {"processed": 0, "success": 0, "failed": 0}

        for chunk in chunks:
            # Metadaten für den Chunk sammeln
            metadata_dict = await self._get_batch_metadata(chunk)

            # Verarbeite alle Dateien im Chunk parallel
            results = await asyncio.gather(*[self.fix_file(f) for f in chunk])

            # Statistiken aktualisieren
            total_stats["processed"] += len(chunk)
            total_stats["success"] += sum(1 for r in results if r)
            total_stats["failed"] += sum(1 for r in results if not r)

            # Kurze Pause zwischen Chunks
            await asyncio.sleep(0.1)

        return total_stats

    # Implementierung von Verbesserungsvorschlag #1: Verbesserte Caching-Strategie
    def optimize_cache_sizes(self) -> None:
        """
        Passt die Cache-Größen basierend auf der verfügbaren Systemressourcen an
        """
        import psutil

        try:
            # Verfügbaren Arbeitsspeicher ermitteln
            available_memory = psutil.virtual_memory().available

            # Cache-Größen anpassen (in MB)
            memory_threshold = 4 * 1024 * 1024 * 1024  # 4 GB

            # Großer Cache bei genügend RAM
            if available_memory > memory_threshold:
                sanitize_filename.cache_clear()
                extract_featured_artist.cache_clear()
                clean_artist_name.cache_clear()
                extract_main_artist.cache_clear()
                # Caches mit neuen Größen erstellen
                sanitize_filename.__wrapped__ = lru_cache(maxsize=8192)(
                    sanitize_filename.__wrapped__
                )
                extract_featured_artist.__wrapped__ = lru_cache(maxsize=4096)(
                    extract_featured_artist.__wrapped__
                )
                clean_artist_name.__wrapped__ = lru_cache(maxsize=4096)(
                    clean_artist_name.__wrapped__
                )
                extract_main_artist.__wrapped__ = lru_cache(maxsize=4096)(
                    extract_main_artist.__wrapped__
                )

            logger.info(
                f"Cache-Größen optimiert basierend auf {available_memory/(1024*1024):.0f}MB verfügbarem RAM"
            )

        except Exception as e:
            logger.warning(f"Cache-Optimierung fehlgeschlagen: {e}")

    # Implementierung von Verbesserungsvorschlag #4: String-Operationen optimieren
    def create_optimized_string_processors(self) -> None:
        """
        Erstellt optimierte String-Verarbeitungsfunktionen mit vorcompilierten Patterns
        """
        # Schon teilweise implementiert durch kompilierte RegEx-Patterns
        # Zusätzliche String-Interning für häufige Strings
        from sys import intern

        # Häufige Strings als Konstanten definieren und intern() verwenden
        self._common_strings = {
            "unknown_artist": intern("Unknown Artist"),
            "singles": intern("Singles"),
            "unknown_album": intern("Unknown Album"),
            "default_year": intern(str(datetime.now().year)),
        }

        logger.debug("Optimierte String-Prozessoren erstellt")

    # Implementierung von Verbesserungsvorschlag #10: Verbesserte Logging-Funktionalität
    def configure_logging(
        self, log_level: int = logging.INFO, log_file: Optional[str] = None
    ) -> None:
        """Konfiguriert das Logging mit strukturierten Logs"""
        import json

        # Basis-Logging-Konfiguration
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        # Logger für diese Klasse einstellen
        self._logger = logging.getLogger(f"{__name__}.FilenameFixerTool")
        self._logger.setLevel(log_level)

        # Bestehende Handler entfernen
        for handler in self._logger.handlers[:]:
            self._logger.removeHandler(handler)

        # Console-Handler hinzufügen
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format))
        self._logger.addHandler(console_handler)

        # Datei-Handler bei Bedarf hinzufügen
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter(log_format))
            self._logger.addHandler(file_handler)

        # JSON-Handler für strukturierte Logs
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "name": record.name,
                    "message": record.getMessage(),
                }
                if hasattr(record, "data"):
                    log_data["data"] = record.data
                return json.dumps(log_data)

        # JSON-Datei-Handler hinzufügen wenn log_file angegeben
        if log_file:
            json_handler = logging.FileHandler(f"{log_file}.json")
            json_handler.setFormatter(JsonFormatter())
            self._logger.addHandler(json_handler)

        self._logger.info("Logging konfiguriert")


async def main():
    """
    Hauptfunktion für die Kommandozeilenausführung.
    Verarbeitet Argumente und startet die Dateiorganisation.
    """
    # Importiere notwendige Module
    import argparse
    import time
    import asyncio
    import logging

    # Argumentparser erstellen
    parser = argparse.ArgumentParser(description="Optimierter Music File Organizer")
    parser.add_argument("--source", help="Quellverzeichnis")
    parser.add_argument("--target", help="Zielverzeichnis")
    parser.add_argument("--fail", help="Fehlerverzeichnis")
    parser.add_argument("--scan", action="store_true", help="Bibliothek scannen")
    parser.add_argument("--debug", action="store_true", help="Debug-Logging aktivieren")
    parser.add_argument("--log-file", help="Logdatei")
    parser.add_argument(
        "--optimize-cache", action="store_true", help="Cache-Größen optimieren"
    )
    args = parser.parse_args()

    # Logging konfigurieren
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename=args.log_file,
    )

    # Informationen ausgeben
    logger.info(f"Music File Organizer gestartet - {datetime.now()}")

    # FilenameFixerTool initialisieren
    fixer = FilenameFixerTool(
        source_dir=args.source, library_dir=args.target, fail_dir=args.fail
    )

    # Cache-Größen optimieren falls gewünscht
    if args.optimize_cache:
        fixer.optimize_cache_sizes()

    # Logging für FilenameFixerTool konfigurieren
    fixer.configure_logging(log_level=log_level, log_file=args.log_file)

    # String-Prozessoren optimieren
    fixer.create_optimized_string_processors()

    # Verarbeitung starten
    start_time = time.time()

    try:
        if args.scan:
            logger.info("Scanmodus aktiviert - noch nicht implementiert")
            # Hier würde die Scan-Logik implementiert werden
            pass
        else:
            # Verzeichnis verarbeiten
            await fixer.process_directory()

    except Exception as e:
        logger.error(f"Kritischer Fehler: {e}")
        import traceback

        logger.error(traceback.format_exc())

    finally:
        # Gesamtlaufzeit ausgeben
        elapsed = time.time() - start_time
        logger.info(f"Programm beendet. Gesamtlaufzeit: {elapsed:.2f} Sekunden")


if __name__ == "__main__":
    asyncio.run(main())
