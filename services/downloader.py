# yt_music_bot/downloader.py
import os
import re
import asyncio
import logging
import functools
import time
from datetime import datetime, timedelta
from typing import Union, List, Dict, Any, Optional, Tuple
from pathlib import Path
from mutagen.mp4 import MP4, MP4Cover
import aiohttp
import yt_dlp
from telegram import Update
from telegram.ext import ContextTypes
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from abc import ABC, abstractmethod
from contextlib import contextmanager

from config import Config
from logger import log_warning, log_debug, log_error, log_info
from utils import (
    MetadataManager,
    sanitize_filename,
    verify_file,
    safe_rename,
    FilenameFixerTool,
)
from metadata import process_metadata
from klassen.title_cleaner import TitleCleaner
from klassen.clean_artist import CleanArtist
from klassen.cover_fixer import CoverFixer  # Neuer Import
from services.organizer import MusicOrganizer
from cookie_handler import CookieHandler
from helfer.artist_map import artist_rules, ARTIST_NAME_OVERRIDES

# Import der benötigten Funktionen aus MetadataManager
escape_markdown_v2 = MetadataManager.escape_markdown_v2

logger = logging.getLogger(__name__)


# -------------------------------------------------------------
# Hilfsklassen und Utilities
# -------------------------------------------------------------


@contextmanager
def track_performance(name: str):
    """Context Manager zum Tracken der Performance von Codeblöcken."""
    start = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start
        logger.debug(f"Performance: {name} took {duration:.2f}s")


class MyLogger:
    def debug(self, msg):
        logger.debug(msg)

    def info(self, msg):
        logger.info(msg)

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        log_error(msg) # Verwendet die log_error Funktion aus utils


class FileUtils:
    @staticmethod
    async def verify_file(path: Union[str, Path]) -> bool:
        """Überprüft, ob eine Datei existiert und größer als 0 Bytes ist."""
        path = Path(path)
        if not path.exists():
            logger.debug(f"Datei existiert nicht: {path}")
            return False
        if path.stat().st_size == 0:
            logger.warning(f"Leere Datei gefunden, wird gelöscht: {path}")
            path.unlink(missing_ok=True)
            return False
        logger.debug(f"Datei validiert: {path}")
        return True

    @staticmethod
    async def safe_rename(src: Union[str, Path], dest: Union[str, Path]) -> None:
        """Verschiebt eine Datei und erstellt Zielverzeichnisse falls nötig."""
        src_path = Path(src)
        dest_path = Path(dest)

        logger.debug(f"Verschiebe Datei von '{src_path}' nach '{dest_path}'")

        if not src_path.exists():
            logger.error(f"Quelldatei existiert nicht für safe_rename: {src}")
            raise FileNotFoundError(f"Quelldatei existiert nicht: {src}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.exists():
            logger.warning(f"Zieldatei existiert bereits, wird überschrieben: {dest_path}")
            dest_path.unlink()

        src_path.rename(dest_path)
        logger.info(f"Datei erfolgreich verschoben: {src_path} -> {dest_path}")

    @staticmethod
    async def clean_temp_files(directory: Union[str, Path] = None):
        """Bereinigt alte Dateien im Download-Verzeichnis"""
        directory = directory or Config.DOWNLOAD_DIR
        now = time.time()
        logger.debug(f"Starte Bereinigung temporärer Dateien in: {directory}")
        cleanup_count = 0
        for f in Path(directory).glob("*"):
            if (now - f.stat().st_mtime) > 3600:  # >1 Stunde alt
                try:
                    f.unlink()
                    logger.debug(f"Temp-Datei bereinigt: {f}")
                    cleanup_count += 1
                except Exception as e:
                    logger.warning(f"Bereinigung fehlgeschlagen: {f}", exc_info=True)
        if cleanup_count > 0:
            logger.info(f"{cleanup_count} temporäre Dateien bereinigt.")
        else:
            logger.debug("Keine alten temporären Dateien gefunden, die bereinigt werden müssen.")


class ProgressTracker:
    def __init__(self, update: Update, total_items: int = 1):
        self.update = update
        self.total_items = total_items
        self.processed_items = 0
        self.last_update_time = datetime.now()
        self.start_time = datetime.now()
        self.update_interval = 5  # Sekunden zwischen Updates
        self.current_item = ""
        logger.debug(f"ProgressTracker initialisiert für {total_items} Items.")

    async def update_progress(self, message: str = None) -> None:
        """Aktualisiert den Fortschritt, aber nicht zu oft."""
        self.processed_items += 1
        now = datetime.now()
        time_diff = (now - self.last_update_time).total_seconds()

        # Aktualisiere nur, wenn genug Zeit vergangen ist oder bei bestimmten Meilensteinen
        if (
            time_diff > self.update_interval
            or self.processed_items == self.total_items
            or self.processed_items % 10 == 0
        ):
            if not message:
                # Berechne ETA basierend auf Durchschnittszeit pro Item
                if self.processed_items > 0:
                    elapsed = (now - self.start_time).total_seconds()
                    eta = (elapsed / self.processed_items) * (
                        self.total_items - self.processed_items
                    )
                    message = (
                        f"⏳ Fortschritt: {self.processed_items}/{self.total_items} "
                        f"({int(self.processed_items/self.total_items*100)}%) | "
                        f"ETA: {eta:.1f}s"
                    )
                    if self.current_item:
                        message += f" | {self.current_item}"
                else:
                    message = f"⏳ Fortschritt: {self.processed_items}/{self.total_items} ({int(self.processed_items/self.total_items*100)}%)"
            
            logger.debug(f"Sende Fortschritts-Update: {message}")
            try:
                # Vermeide zu viele Updates, wenn das update-Objekt nicht mehr gültig ist
                await self.update.message.reply_text(message)
            except Exception as e:
                logger.warning(f"Konnte Fortschrittsnachricht nicht senden: {e}")
            self.last_update_time = now

    def set_current_item(self, item_name: str) -> None:
        """Setzt den Namen des aktuellen Items für die Fortschrittsanzeige."""
        self.current_item = item_name
        logger.debug(f"Aktuelles Item gesetzt: {item_name}")


def _progress_hook(progress_tracker, d):
    """Hook für den Download-Fortschritt."""
    if d["status"] == "downloading":
        # Hier könnte der Progress-Tracker verwendet werden
        # Wegen der Flut von Events verwenden wir ihn aber nicht direkt hier
        pass
    elif d["status"] == "finished":
        logger.info(f"Download abgeschlossen: {d['filename']}")
    elif d["status"] == "error":
        logger.error(f"Download-Fehler im Progress-Hook: {d['filename']} - {d.get('error', 'Unbekannt')}")


def _validate_youtube_url(url: str) -> Optional[str]:
    """Validiert und normalisiert eine YouTube-URL."""
    if not url:
        logger.debug("URL ist leer.")
        return None
    url = url.strip()
    logger.info(f"[DEBUG] Prüfe URL: {url}")
    video_id_pattern = r"[0-9A-Za-z_-]{11}"

    # Playlist-URLs
    playlist_patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=([\w-]+)"
    ]
    for pattern in playlist_patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            logger.debug(f"Playlist-URL erkannt: {url}")
            return f"https://www.youtube.com/playlist?list={match.group(1)}"

    # Video-URLs
    video_patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([\w-]{11})",
        r"(?:https?://)?(?:www\.)?youtu\.be/([\w-]{11})",
    ]
    for pattern in video_patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match and re.match(f"^{video_id_pattern}$", match.group(1)):
            logger.debug(f"Video-URL erkannt: {url}")
            return f"https://www.youtube.com/watch?v={match.group(1)}"

    # Fallback für andere URL-Formate
    fallback = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})(?:\?|&|/|$)", url)
    if fallback:
        logger.debug(f"Fallback Video-ID gefunden: {fallback.group(1)}")
        return f"https://www.youtube.com/watch?v={fallback.group(1)}"

    logger.warning(f"[DEBUG] URL konnte nicht validiert werden: {url}")
    return None


# -------------------------------------------------------------
# Spezifische Fehlerklassen
# -------------------------------------------------------------


class DownloadError(Exception):
    base_message = "Download-Fehler"

    def __init__(self, details: str = "", code: str = "GENERIC"):
        self.code = code
        self.details = details
        super().__init__(f"{self.base_message} [{code}]: {details}")
        logger.debug(f"DownloadError erstellt: {self}")


class InvalidURLError(DownloadError):
    base_message = "Ungültige YouTube-URL"
    code = "INVALID_URL"

    def __init__(self, details: str = ""):
        self.details = details
        super().__init__(f"{self.base_message}: {details}", code=self.code)
        logger.debug(f"InvalidURLError erstellt: {self}")


class FormatNotAvailableError(DownloadError):
    base_message = "Format nicht verfügbar"
    code = "FORMAT_MISSING"

    def __init__(self, details: str = ""): # Details hinzugefügt
        self.details = details
        super().__init__(f"{self.base_message}: {details}", code=self.code)
        logger.debug(f"FormatNotAvailableError erstellt: {self}")


class MetadataError(DownloadError):
    base_message = "Metadaten-Fehler"
    code = "METADATA_ERROR"

    def __init__(self, details: str = ""): # Details hinzugefügt
        self.details = details
        super().__init__(f"{self.base_message}: {details}", code=self.code)
        logger.debug(f"MetadataError erstellt: {self}")


class FileProcessingError(DownloadError):
    base_message = "Dateifehler"
    code = "FILE_ERROR"

    def __init__(self, details: str = ""): # Details hinzugefügt
        self.details = details
        super().__init__(f"{self.base_message}: {details}", code=self.code)
        logger.debug(f"FileProcessingError erstellt: {self}")


# -------------------------------------------------------------
# Abstrakte Konfigurations-Klasse für Dependency Injection
# -------------------------------------------------------------


class IDownloaderConfig(ABC):
    @property
    @abstractmethod
    def AUDIO_FORMAT(self) -> str:
        pass

    @property
    @abstractmethod
    def AUDIO_FORMAT_STRING(self) -> str:
        pass

    @property
    @abstractmethod
    def AUDIO_QUALITY(self) -> int:
        pass

    @property
    @abstractmethod
    def DOWNLOAD_DIR(self) -> str:
        pass

    @property
    @abstractmethod
    def PROCESSED_DIR(self) -> str:
        pass

    @property
    @abstractmethod
    def MAX_DURATION(self) -> int:
        pass

    @property
    @abstractmethod
    def MAX_PLAYLIST_ITEMS(self) -> int:
        pass

    @property
    @abstractmethod
    def DEFAULT_ALBUM_NAME(self) -> str:
        pass

    @property
    @abstractmethod
    def UNKNOWN_PLAYLIST(self) -> str:
        pass

    @property
    @abstractmethod
    def MAX_CONCURRENT_DOWNLOADS(self) -> int:
        pass

    @property
    @abstractmethod
    def METADATA_DEFAULTS(self) -> Dict[str, Any]:
        pass

    @property
    @abstractmethod
    def LIBRARY_DIR(self) -> str:
        pass # Hinzugefügt, da MusicOrganizer dies benötigt


# -------------------------------------------------------------
# Abstrakte Klasse für Downloader
# -------------------------------------------------------------


class IDownloader(ABC):
    @abstractmethod
    async def download_audio(self, url: str) -> Union[str, List[str]]:
        """Abstrakte Methode für Audio-Downloads."""
        pass


# -------------------------------------------------------------
# Metadaten-Handler für bessere Trennung der Zuständigkeiten
# -------------------------------------------------------------


class MetadataHandler:
    def __init__(self, metadata_manager: MetadataManager, cover_fixer: CoverFixer):
        self.metadata_manager = metadata_manager
        self.cover_fixer = cover_fixer  # Neue Instanz von CoverFixer
        self._metadata_cache = {}
        self._cache_expiry = timedelta(hours=1)
        logger.debug("MetadataHandler initialisiert mit CoverFixer.")

    async def _clean_cache(self):
        """Leert abgelaufene Cache-Einträge."""
        now = datetime.now()
        old_cache_size = len(self._metadata_cache)
        self._metadata_cache = {
            k: v
            for k, v in self._metadata_cache.items()
            if (now - v["timestamp"]) < self._cache_expiry
        }
        cleaned_count = old_cache_size - len(self._metadata_cache)
        if cleaned_count > 0:
            logger.debug(f"{cleaned_count} Metadaten-Cache-Einträge bereinigt.")

    async def enrich_track_metadata(
        self, info: Dict[str, Any], playlist_metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Anreicherung von Metadaten mit Caching."""
        logger.debug(f"Starte Anreicherung von Metadaten für {info.get('title', 'unbekannt')}")
        cache_key = f"{info.get('id', '')}-{hash(str(info))}"

        if len(self._metadata_cache) > 800:
            await self._clean_cache()

        if cache_key in self._metadata_cache:
            cached = self._metadata_cache[cache_key]
            if (datetime.now() - cached["timestamp"]) < self._cache_expiry:
                logger.debug(f"Metadaten aus Cache geladen für: {info.get('title')}")
                return cached["data"]

        # Metadaten anreichern
        enriched = await process_metadata(info)
        logger.debug(f"Metadaten angereichert (Initial): {enriched}")

        # Album-Artist aus dem ersten Künstler extrahieren
        artist_name = enriched.get("artist", "")
        if artist_name:
            enriched["album_artist"] = re.split(
                r"[,x&]|feat\.?", artist_name, maxsplit=1
            )[0].strip()
        else:
            enriched["album_artist"] = "Various Artists"
        logger.debug(f"Album-Artist gesetzt zu: {enriched['album_artist']}")

        # Playlist-spezifische Metadaten hinzufügen wenn vorhanden
        if playlist_metadata:
            enriched.update(
                {
                    "album": playlist_metadata.get("album", Config.DEFAULT_ALBUM_NAME),
                    "track_number": playlist_metadata.get("track_number", 1),
                    "total_tracks": playlist_metadata.get("total_tracks", 0),
                }
            )
            logger.debug(f"Playlist-Metadaten angewendet: {playlist_metadata.get('album')}")
        else:
            enriched.setdefault("album", Config.DEFAULT_ALBUM_NAME)
            logger.debug(f"Album-Name auf Standard gesetzt: {enriched['album']}")

        # Cover-Daten werden in process_metadata abgerufen (via CoverFixer)
        # Hier keine zusätzliche Verarbeitung nötig, da cover_data bereits in enriched enthalten ist

        self._metadata_cache[cache_key] = {
            "data": enriched,
            "timestamp": datetime.now(),
        }
        logger.debug(f"Metadaten im Cache gespeichert für: {info.get('title')}")

        return enriched

    async def write_metadata(
        self, src_path: str, metadata: Dict[str, Any], dest_path: str
    ) -> None:
        """Schreibt Metadaten in eine Audiodatei."""
        logger.debug(f"Schreibe Metadaten in '{src_path}'")
        try:
            audio = MP4(src_path)

            def safe(val, fallback=""):
                return str(val) if val is not None else fallback

            audio["\xa9nam"] = safe(metadata.get("title", ""))
            audio["\xa9ART"] = safe(metadata.get("artist", "Unknown Artist"))
            audio["\xa9alb"] = safe(metadata.get("album", Config.DEFAULT_ALBUM_NAME))
            audio["aART"] = safe(
                metadata.get("album_artist", metadata.get("artist", "Various Artists"))
            )
            audio["\xa9day"] = safe(metadata.get("year", datetime.now().year))
            audio["\xa9gen"] = safe(
                metadata.get("genre", Config.METADATA_DEFAULTS.get("genre", "Unknown"))
            )
            audio["trkn"] = [
                (metadata.get("track_number", 1), metadata.get("total_tracks", 0))
            ]
            if metadata.get("lyrics"):
                audio["\xa9lyr"] = metadata["lyrics"]

            # Cover einbetten mit CoverFixer
            if metadata.get("cover_data"):
                if self.cover_fixer.embed_cover(audio, metadata["cover_data"]):
                    logger.debug("Cover erfolgreich eingebettet.")
                else:
                    logger.warning("Cover konnte nicht eingebettet werden.")
            else:
                logger.debug("Kein Cover-Daten in Metadaten gefunden.")

            audio.save()
            logger.info(f"Metadaten erfolgreich in '{src_path}' geschrieben.")
            await self.file_utils.safe_rename(src_path, dest_path)
            logger.info(f"Datei erfolgreich verschoben: {dest_path}")

        except Exception as e:
            logger.error(f"Metadaten-Schreibfehler: {str(e)}", extra={"file": src_path}, exc_info=True)
            raise MetadataError(f"Fehler beim Schreiben der Metadaten: {str(e)}")

    async def _add_thumbnail(self, audio: MP4, thumbnail_url: str) -> None:
        """Veraltete Methode, wird durch CoverFixer ersetzt."""
        logger.warning("Deprecated: _add_thumbnail aufgerufen. Verwende stattdessen CoverFixer.")
        # Diese Methode wird nicht mehr benötigt, da CoverFixer die Cover-Verarbeitung übernimmt

    async def _batch_download_thumbnails(self, metadata_list: List[Dict[str, Any]]) -> List[bytes]:
        """Veraltete Methode, wird durch CoverFixer ersetzt."""
        logger.warning("Deprecated: _batch_download_thumbnails aufgerufen. Verwende stattdessen CoverFixer.")
        return []

    async def _download_thumbnail(self, session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
        """Veraltete Methode, wird durch CoverFixer ersetzt."""
        logger.warning("Deprecated: _download_thumbnail aufgerufen. Verwende stattdessen CoverFixer.")
        return None


# -------------------------------------------------------------
# Playlist-Processor für Playlist-spezifische Logik
# -------------------------------------------------------------


class PlaylistProcessor:
    def __init__(
        self,
        update: Update,
        metadata_handler: MetadataHandler,
        file_utils: FileUtils,
        config: IDownloaderConfig = None,
    ):
        self.update = update
        self.metadata_handler = metadata_handler
        self.file_utils = file_utils
        self.config = config or Config
        # Cache für bereits verarbeitete Video-IDs, nur Strings als Keys verwenden
        self.download_cache = {}
        # Cache für fehlgeschlagene Tracks, verwende IDs oder Indizes anstelle von Dictionaries
        self.failed_tracks = set()
        logger.debug("PlaylistProcessor initialisiert.")

    def _validate_playlist_entry(self, entry):
        """Überprüft, ob ein Playlist-Eintrag gültig ist."""
        is_valid = isinstance(entry, dict) and "id" in entry
        if not is_valid:
            logger.warning(f"Ungültiger Playlist-Eintrag erkannt: {entry}")
        return is_valid

    async def process_playlist(
        self, info: Dict[str, Any], ydl: yt_dlp.YoutubeDL
    ) -> List[str]:
        """Verarbeitet eine Playlist mit Thread-Pool für bessere Parallelisierung."""
        logger.debug(f"Starte Playlist-Verarbeitung für: {info.get('title')}")
        with track_performance("Playlist-Verarbeitung"):
            # Filtere ungültige Einträge
            entries = [
                e for e in info.get("entries", []) if self._validate_playlist_entry(e)
            ]
            if len(entries) != len(info.get("entries", [])):
                logger.warning(
                    "Einige Playlist-Einträge wurden wegen ungültigem Format verworfen"
                )

            if not entries:
                await self.update.message.reply_text(
                    "❌ Keine gültigen Einträge in der Playlist"
                )
                logger.info("Keine gültigen Einträge in der Playlist gefunden.")
                return []

            playlist_name = info.get("title", Config.UNKNOWN_PLAYLIST)
            uploader = info.get("uploader", "Various Artists")

            playlist_metadata = {
                "album": playlist_name,
                "album_artist": uploader,
                "total_tracks": len(entries),
            }
            logger.debug(f"Playlist-Metadaten: {playlist_metadata}")

            # Erstelle einen Progress-Tracker für die Playlist
            progress_tracker = ProgressTracker(self.update, len(entries))
            await self.update.message.reply_text(
                f"⬇️ Verarbeite Playlist: {playlist_name} ({len(entries)} Titel)"
            )
            logger.info(f"Starte Download von {len(entries)} Titeln in Playlist '{playlist_name}'.")

            # Automatische Semaphore-Größe anhand der CPU-Kapazität
            max_concurrent = min(
                self.config.MAX_CONCURRENT_DOWNLOADS,
                (os.cpu_count() or 1) * 2,  # 2 Tasks pro CPU-Kern
            )
            logger.debug(f"Maximale parallele Downloads: {max_concurrent}")
            # Semaphore für die Parallelverarbeitung
            semaphore = asyncio.Semaphore(max_concurrent)

            # Erstelle Tasks für alle Playlist-Einträge mit verbesserter Fehlerbehandlung
            tasks = []
            for idx, entry in enumerate(entries):
                track_metadata = dict(playlist_metadata)
                track_metadata["track_number"] = idx + 1

                # Verbesserte Fehlerbehandlung mit Retry-Logik
                task = asyncio.create_task(
                    self._process_playlist_entry_with_retry(
                        entry=entry,
                        idx=idx,
                        playlist_metadata=track_metadata,
                        ydl=ydl,
                        semaphore=semaphore,
                        progress_tracker=progress_tracker,
                    )
                )
                tasks.append(task)

            # Sammle Ergebnisse
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful_downloads = [r for r in results if isinstance(r, str) and r]
            logger.info(f"Playlist-Verarbeitung abgeschlossen. Erfolgreiche Downloads: {len(successful_downloads)}")

            # Fehler identifizieren
            errors = [r for r in results if isinstance(r, Exception)]
            if errors:
                logger.error(f"{len(errors)} Fehler bei der Playlist-Verarbeitung.")
                for e in errors[:5]:  # Zeige die ersten 5 Fehler
                    logger.error(f"Detaillierter Playlist-Fehler: {type(e).__name__}: {str(e)}")

            # Statusmeldung
            await self.update.message.reply_text(
                f"✅ {len(successful_downloads)}/{len(entries)} Titel erfolgreich verarbeitet"
            )

            return successful_downloads

    async def _process_playlist_entry_with_retry(
        self,
        entry,
        idx,
        playlist_metadata,
        ydl,
        semaphore,
        progress_tracker=None,
        max_retries=2,
    ):
        """Verarbeitet einen Playlist-Eintrag mit Retry-Logik und besserer Fehlerbehandlung."""
        track_id = entry.get("id") or entry.get("title") or f"idx-{idx}"
        logger.debug(f"Starte _process_playlist_entry_with_retry für Track {idx+1} (ID: {track_id})")
        try:
            if not isinstance(entry, dict):
                logger.error(f"Ungültiger Eintragstyp in Playlist: {type(entry)} statt dict")
                raise ValueError("Playlist-Eintrag muss ein Dictionary sein")

            # Konvertiere komplexe Objekte zu Strings fürs Logging
            safe_entry = {
                k: str(v) for k, v in entry.items() if not isinstance(v, (dict, list))
            }

            # Überprüfe, ob der Track bereits fehlgeschlagen ist
            if track_id in self.failed_tracks:
                logger.info(f"Überspringe bereits fehlgeschlagenen Track: {track_id}")
                return None

            # Aktuelles Item in Progress-Tracker setzen
            if progress_tracker:
                progress_tracker.set_current_item(entry.get("title", f"Track {idx+1}"))

            # Debug-Logging
            logger.debug(f"Verarbeite Eintrag: {entry.get('id')}, Typ: {type(entry)}")

            # Retry-Schleife
            for attempt in range(max_retries + 1):
                try:
                    async with semaphore:
                        result = await self._process_playlist_entry(
                            entry, idx, playlist_metadata, ydl
                        )
                        if result:
                            logger.info(f"Track {idx+1} erfolgreich in Versuch {attempt+1}")
                            return result
                        elif attempt < max_retries:
                            logger.info(f"Track {idx+1} lieferte kein Ergebnis in Versuch {attempt+1}. Wiederhole...")
                            await asyncio.sleep(2**attempt)  # Exponentielles Backoff
                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(
                            f"Versuch {attempt+1} für Track {idx+1} fehlgeschlagen: {e}. Wiederhole...", exc_info=True
                        )
                        await asyncio.sleep(2**attempt)  # Exponentielles Backoff
                    else:
                        logger.error(f"Alle Versuche für Track {idx+1} fehlgeschlagen: {e}", exc_info=True)
                        raise

            return None

        except Exception as e:
            # Bei Fehler den Track als fehlgeschlagen markieren
            self.failed_tracks.add(track_id)
            logger.error(
                f"Endgültiger Fehler bei Track {idx+1}: {str(e)}",
                extra={"entry": safe_entry, "error": str(e)}, exc_info=True
            )
            return None

    async def _process_playlist_entry(
        self, entry, idx, playlist_metadata, ydl
    ) -> Optional[str]:
        """Asynchrone Verarbeitung eines einzelnen Playlist-Eintrags mit Cache-Check."""
        video_id = entry.get("id") # String-Key für Cache verwenden
        logger.debug(f"Starte _process_playlist_entry für Video-ID: {video_id}")
        try:
            # Sicherstellen, dass entry ein Dict ist und die nötigen Daten enthält
            if not isinstance(entry, dict) or "id" not in entry:
                logger.error(f"Ungültiger Playlist-Eintrag für Verarbeitung: {entry}")
                return None

            if video_id in self.download_cache:
                logger.info(f"Track {video_id} aus Playlist-Cache geladen.")
                return self.download_cache[video_id]

            # Führe den Download hier durch, da Playlist-Items oft nur Info-Dics sind
            # und nicht direkt vollständige Download-Pfade enthalten.
            # Wir benötigen dafür ein yt_dlp-Objekt, das wir von oben mitbekommen.
            try:
                # Da wir hier schon im yt_dlp Kontext sind, können wir extract_info direkt verwenden
                # download=True sorgt dafür, dass die Datei auch physikalisch heruntergeladen wird.
                # Hier muss man vorsichtig sein, da _download_with_retry dies bereits tut.
                # Dieses Szenario ist komplex, da ytdlp Playlists als Batch herunterladen kann,
                # aber wir jeden Eintrag einzeln verarbeiten wollen.
                # Eine bessere Strategie wäre, den Download des Eintrags direkt hier auszulösen
                # anstatt über extract_info den Pfad zu finden, wenn extract_info bereits download=True macht.

                # Für diese Korrektur angenommen, dass 'entry' bereits die notwendigen Download-Informationen enthält
                # oder ydl.prepare_filename funktioniert auch für Info-Dics vor dem eigentlichen Download.
                # Wenn nicht, müsste hier ein `ydl.download([entry['webpage_url']])` aufgerufen werden.
                
                # Der Pfad wird von yt_dlp generiert. Wir versuchen ihn zu erraten
                # oder holen ihn aus dem resultierenden info-dict, falls der Download hier stattfindet.
                
                # Wenn `_download_with_retry` für jeden einzelnen Eintrag aufgerufen wird,
                # dann wird `_process_playlist_entry` eigentlich nur das Ergebnis nach der Verarbeitung
                # von `_process_single_track` übernehmen.
                # Aktuell ist die Logik so, dass _download_with_retry die ganze Playlist auf einmal lädt
                # und _process_playlist_entry dann die bereits heruntergeladenen (oder teilweise verarbeiteten) Einträge erhält.
                # Das ist eine Diskrepanz, die man klären muss.
                # Gehen wir davon aus, dass 'entry' nach dem `ydl.extract_info(url, download=True)` in `_download_with_retry`
                # bereits einen 'filepath' oder 'filename' hat.

                temp_file = Path(ydl.prepare_filename(entry)).with_suffix(
                    f".{self.config.AUDIO_FORMAT}"
                )
                logger.debug(f"Erwarteter temporärer Dateipfad für {video_id}: {temp_file}")


            except Exception as e:
                logger.error(f"Fehler beim Vorbereiten des Dateinamens für {video_id}: {e}", exc_info=True)
                raise FileProcessingError(f"Dateiname konnte nicht vorbereitet werden für {video_id}: {str(e)}")

            # Überprüfe, ob die Datei existiert und gültig ist
            if not await self.file_utils.verify_file(temp_file):
                logger.warning(f"Datei existiert nicht oder ist ungültig für {video_id}: {temp_file}. Überspringe.")
                return None

            # Metadaten anreichern
            enriched = await self.metadata_handler.enrich_track_metadata(
                entry, playlist_metadata
            )
            logger.debug(f"Metadaten angereichert für {video_id}: {enriched}")

            # Dateinamen mit Tracknummer generieren
            filename = sanitize_filename(
                f"{enriched['track_number']:02d} - {enriched['artist']} - {enriched['title']}"
            )
            final_path = (
                Path(self.config.PROCESSED_DIR)
                / f"{filename}.{self.config.AUDIO_FORMAT}"
            )
            logger.debug(f"Finaler Dateipfad für {video_id}: {final_path}")

            # Zentrale Dateiverarbeitungsmethode verwenden
            await self._process_file(temp_file, enriched, final_path)
            logger.info(f"Track {video_id} erfolgreich verarbeitet und verschoben zu: {final_path}")

            # Ergebnis im Cache speichern
            self.download_cache[video_id] = str(final_path)

            return str(final_path)

        except Exception as e:
            # Bei Fehler den Track als fehlgeschlagen markieren
            self.failed_tracks.add(video_id) # video_id ist ein String
            logger.error(f"Fehler bei _process_playlist_entry für Track {video_id}: {str(e)}", exc_info=True)
            return None

    async def _process_file(
        self, temp_path: Path, metadata: dict, final_path: Path
    ) -> Path:
        """Zentrale Methode für alle Dateioperationen"""
        logger.debug(f"Starte Dateiverarbeitung: temp='{temp_path}', final='{final_path}'")
        try:
            # 1. Metadaten schreiben
            await self.metadata_handler.write_metadata(
                str(temp_path), metadata, str(final_path)
            )
            logger.debug(f"Metadaten geschrieben für: {temp_path.name}")

            # 2. Datei verschieben
            await self.file_utils.safe_rename(str(temp_path), str(final_path))
            logger.debug(f"Datei verschoben von '{temp_path.name}' zu '{final_path.name}'")

            return final_path
        except MetadataError as e:
            logger.error(f"Metadatenfehler in _process_file: {str(e)}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Dateiverarbeitung fehlgeschlagen in _process_file: {str(e)}", exc_info=True)
            raise FileProcessingError(f"Fehler bei der Dateiverarbeitung: {str(e)}")


# -------------------------------------------------------------
# Haupt-Downloader-Klasse
# -------------------------------------------------------------


class YoutubeDownloader(IDownloader):
    def __init__(
        self,
        update: Update,
        config: IDownloaderConfig = None,
        metadata_manager=None,
        cookie_handler=None,
    ):
        self.update = update
        self.config = config or Config()
        self.file_utils = FileUtils()
        self.metadata_manager = metadata_manager or MetadataManager()
        self.cookie_handler = cookie_handler or CookieHandler()
        
        # Initialisiere Clients für CoverFixer
        from klassen.musicbrainz_client import MusicBrainzClient
        from klassen.genius_client import GeniusClient
        from klassen.lastfm_client import LastFMClient
        self.artist_cleaner = CleanArtist(artist_rules=artist_rules, artist_overrides=ARTIST_NAME_OVERRIDES)
        self.musicbrainz_client = MusicBrainzClient(self.artist_cleaner)
        self.genius_client = GeniusClient(self.artist_cleaner)
        self.lastfm_client = LastFMClient()
        self.cover_fixer = CoverFixer(self.musicbrainz_client, self.genius_client, self.lastfm_client)
        
        self.metadata_handler = MetadataHandler(self.metadata_manager, self.cover_fixer)
        self.playlist_processor = PlaylistProcessor(
            update, self.metadata_handler, self.file_utils, self.config
        )
        self.organizer = MusicOrganizer(self.config.LIBRARY_DIR)
        logger.debug(f"YoutubeDownloader initialisiert mit CoverFixer. Library Dir: {self.config.LIBRARY_DIR}")

        self.download_cache = {}
        self.cache_timestamps = {}
        self.cache_expiry = timedelta(hours=1)
        self.failed_tracks = set()

        self.ERROR_MESSAGES = {
            "invalid_url": "❌ Ungültige YouTube-URL",
            "download_failed": "❌ Download fehlgeschlagen (Code: {code})",
            "metadata_error": "❌ Metadaten konnten nicht verarbeitet werden",
            "file_error": "❌ Datei konnte nicht gespeichert werden",
            "critical_error": "❌ Kritischer Fehler: {error}",
            "format_error": "❌ Das angeforderte Format ist nicht verfügbar",
        }

    async def _clean_cache(self):
        """Entfernt abgelaufene Cache-Einträge."""
        now = datetime.now()
        expired_keys = [
            k
            for k, timestamp in self.cache_timestamps.items()
            if (now - timestamp) > self.cache_expiry
        ]

        for key in expired_keys:
            if key in self.download_cache:
                del self.download_cache[key]
            if key in self.cache_timestamps:
                del self.cache_timestamps[key]

        logger.debug(f"{len(expired_keys)} abgelaufene Cache-Einträge entfernt.")

    async def _clean_temp_files(self):
        """Bereinigt alte temporäre Dateien im Download-Verzeichnis."""
        logger.debug("Starte _clean_temp_files im YoutubeDownloader.")
        try:
            now = time.time()
            cleanup_count = 0

            for file_path in Path(self.config.DOWNLOAD_DIR).glob("*"):
                if (
                    file_path.is_file() and (now - file_path.stat().st_mtime) > 3600
                ):  # >1 Stunde alt
                    try:
                        file_path.unlink()
                        cleanup_count += 1
                        logger.debug(f"Temporäre Datei bereinigt: {file_path}")
                    except Exception as e:
                        logger.warning(
                            f"Bereinigung fehlgeschlagen: {file_path}", exc_info=True
                        )

            if cleanup_count > 0:
                logger.info(f"{cleanup_count} temporäre Dateien bereinigt.")
            else:
                logger.debug("Keine alten temporären Dateien gefunden, die bereinigt werden müssen.")

        except Exception as e:
            logger.error(
                f"Fehler bei der Bereinigung temporärer Dateien: {str(e)}",
                exc_info=True,
            )

    def _get_ydl_opts(self, attempt: int = 0, progress_tracker=None) -> Dict[str, Any]:
        logger.debug(f"Erstelle yt-dlp Optionen für Versuch {attempt}")
        opts = {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": self.config.AUDIO_FORMAT,
                "preferredquality": str(self.config.AUDIO_QUALITY),
            }],
            "outtmpl": os.path.join(self.config.DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "writethumbnail": True,
            "ignoreerrors": False,
            "retries": 3,
            "fragment_retries": 3,
            "extractor_args": {
                "youtube": {
                    "skip": ["hls", "dash"],
                    "player_client": ["android", "web"],
                    "timeout": 30,
                }
            },
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
            "compat_opts": ["no-youtube-unavailable-videos"],
            "verbose": True,
            "logger": MyLogger(),
        }

        if self.cookie_handler.has_cookies():
            opts.update({
                "cookiefile": self.cookie_handler.cookie_path,
                "age_limit": 25,
                "extractor_args": {
                    "youtube": {
                        "skip": ["hls", "dash"],
                        "player_skip": ["config"],
                    }
                }
            })
            logger.debug(f"yt-dlp Optionen: Cookie-Datei wird verwendet: {self.cookie_handler.cookie_path}")
        else:
            logger.debug("yt-dlp Optionen: Keine Cookie-Datei gefunden.")

        if progress_tracker:
            opts["progress_hooks"] = [lambda d: _progress_hook(progress_tracker, d)]
            logger.debug("yt-dlp Optionen: Progress-Hook aktiviert.")

        logger.debug(f"Final yt-dlp Optionen: {opts}")
        return opts

    async def download_audio(self, url: str) -> Union[str, List[str]]:
        """
	    Hauptmethode für Audio-Downloads mit verbesserter Fehlerbehandlung und Caching.
	    """
        logger.info(f"download_audio aufgerufen für URL: {url}")
        try:
            await self._clean_temp_files()
            await self._clean_cache()

            validated_url = _validate_youtube_url(url)
            if not validated_url:
                logger.warning(f"URL-Validierung fehlgeschlagen für: {url}")
                raise InvalidURLError(
                    "URL konnte nicht als YouTube-URL validiert werden"
                )
            url = validated_url

            logger.info(
                "Download gestartet",
                extra={
                    "user": self.update.effective_user.id if self.update and self.update.effective_user else "N/A",
                    "url": url,
                    "type": "playlist" if "/playlist?" in url else "single",
                },
            )

            video_id_match = re.search(r"youtube\.com/3([\w-]{11})", url)
            if video_id_match:
                cache_key = video_id_match.group(1)
                if cache_key in self.download_cache:
                    logger.info(f"Video '{cache_key}' aus Cache geladen.")
                    return self.download_cache[cache_key]
                else:
                    logger.debug(f"Video '{cache_key}' nicht im Cache.")
            else:
                logger.debug("Keine Einzelvideo-ID in URL gefunden, überspringe Cache-Prüfung.")

            with track_performance("YouTube-Download"):
                result = await self._download_with_retry(url)
                if not result:
                    raise DownloadError("Kein Ergebnis vom Download")

                # HINWEIS: Dieser Block scheint auf einer alten Logik zu basieren, bei der `result`
                # ein Dictionary ist. Nach aktueller Implementierung ist `result` ein Pfad (str)
                # oder eine Liste von Pfaden. Die eigentliche Bereinigung findet in
                # `_process_single_track` statt. Ich passe es trotzdem an, falls es
                # doch noch einen Codepfad gibt, der hierher führt.
                if isinstance(result, dict):
                    original_title = result.get("title", "")
                    raw_artist = result.get("artist") or result.get("uploader", "")
                    
                    # GEÄNDERT: Verwende die neue artist_cleaner Instanz
                    artist = self.artist_cleaner.clean(raw_artist)
                    
                    # GEÄNDERT: Verwende die importierte TitleCleaner Klasse
                    cleaned_title = TitleCleaner.clean_title(original_title, artist)

                    result["title"] = cleaned_title
                    result["artist"] = artist

                    logger.debug(
                        f"🎧 Titel (in download_audio) bereinigt: '{original_title}' → '{cleaned_title}' (Artist: {artist})"
                    )

            logger.info("Download-Prozess erfolgreich abgeschlossen.")

            with track_performance("Bibliothek-Organisation"):
                # Annahme: FilenameFixerTool ist verfügbar
                from utils import FilenameFixerTool
                fixer = FilenameFixerTool()
                await fixer.process_directory()

            await self.update.message.reply_text(
                "✅ Dateien wurden in die Bibliothek einsortiert."
            )

            if video_id_match and isinstance(result, str):
                cache_key = video_id_match.group(1)
                self.download_cache[cache_key] = result
                self.cache_timestamps[cache_key] = datetime.now()
                logger.debug(f"Cache für Einzelvideo '{cache_key}' aktualisiert.")

            if isinstance(result, str):
                return {
                    "success": True,
                    "file_path": result,
                    "title": Path(result).stem
                }
            else:
                return {
                    "success": False,
                    "error": "Download lieferte kein gültiges Ergebnis zurück"
                }

        except InvalidURLError as e:
            await self._handle_error("invalid_url", {"url": url, "details": e.details})
            return {"success": False, "error": f"Ungültige URL: {str(e)}"}
        except FormatNotAvailableError as e:
            await self._handle_error("format_error", {"details": e.details})
            return {"success": False, "error": f"Format nicht verfügbar: {str(e)}"}
        except DownloadError as e:
            await self._handle_error("download_failed", {"code": e.code, "details": e.details})
            return {"success": False, "error": f"Download fehlgeschlagen: {str(e)}"}
        except MetadataError as e:
            await self._handle_error("metadata_error", {"details": e.details})
            return {"success": False, "error": f"Metadaten-Fehler: {str(e)}"}
        except FileProcessingError as e:
            await self._handle_error("file_error", {"details": e.details})
            return {"success": False, "error": f"Dateifehler: {str(e)}"}
        except Exception as e:
            error_message = f"Ein unerwarteter Fehler ist aufgetreten: {str(e)}"
            await self._handle_error("critical_error", {"error": error_message})
            log_error(f"Kritischer Fehler: {str(e)}", {"url": url, "traceback": True})
            return {"success": False, "error": f"Kritischer Fehler: {str(e)}"}

    async def _download_with_retry(self, url: str, max_retries: int = 3) -> Union[str, List[str]]:
        last_exception = None
        logger.debug(f"Starte Download mit Retries für URL: {url}, max_retries: {max_retries}")

        for attempt in range(max_retries):
            logger.info(f"Download-Versuch {attempt+1}/{max_retries} für URL: {url}")
            try:
                with track_performance(f"Download-Versuch {attempt+1}"):
                    progress_tracker = ProgressTracker(self.update)
                    ydl_opts = self._get_ydl_opts(attempt, progress_tracker)

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        logger.debug(f"yt-dlp Instanz erstellt für Versuch {attempt+1}")
                        info_dict = await asyncio.to_thread(
                            ydl.extract_info, url, download=False
                        )
                        logger.debug(f"Info-Extraktion abgeschlossen für Versuch {attempt+1}.")

                        if not info_dict:
                            logger.warning(
                                f"Keine Videoinformationen in Versuch {attempt+1} für URL: {url}"
                            )
                            await self.update.message.reply_text(
                                "❌ Keine Videoinformationen verfügbar"
                            )
                            continue

                        is_playlist = "entries" in info_dict
                        if is_playlist:
                            entries = list(filter(None, info_dict.get("entries", [])))
                            entries = [e for e in entries if isinstance(e, dict) and 'id' in e]
                            progress_tracker.total_items = len(entries)
                            pool_size = min(
                                self.config.MAX_CONCURRENT_DOWNLOADS,
                                (os.cpu_count() or 1) * 4,
                            )
                            logger.info(
                                f"Playlist erkannt: {len(entries)} Titel. Pool-Größe: {pool_size}."
                            )
                            await self.update.message.reply_text(
                                f"⬇️ Starte Download von {len(entries)} Titeln aus der Playlist: "
                                f"{info_dict.get('title', 'Unbekannt')}"
                            )
                            logger.debug(f"Nachricht für Playlist-Start gesendet.")

                        logger.debug(f"Starte eigentlichen Download für URL: {url}")
                        info = await asyncio.to_thread(
                            ydl.extract_info, url, download=True
                        )
                        logger.debug(f"Download abgeschlossen für URL: {url}.")

                        if not info:
                            logger.warning(
                                f"Keine Download-Informationen nach Download in Versuch {attempt+1} für URL: {url}"
                            )
                            continue

                        logger.info(
                            "Download abgeschlossen",
                            extra={
                                "url": url,
                                "attempt": attempt,
                                "type": "playlist" if is_playlist else "single",
                            },
                        )

                        return await self._process_download_result(info, ydl)

            except yt_dlp.utils.DownloadError as e:
                last_exception = e
                logger.error(f"yt-dlp DownloadError in Versuch {attempt+1}: {str(e)}", exc_info=True)
                if "unavailable" in str(e).lower() or "private" in str(e).lower():
                    await self.update.message.reply_text("❌ Video ist nicht verfügbar oder privat.")
                    raise FormatNotAvailableError(f"Video nicht verfügbar: {str(e)}") from e
                elif "no suitable format" in str(e).lower():
                    await self.update.message.reply_text("❌ Kein passendes Audioformat gefunden.")
                    raise FormatNotAvailableError(f"Kein Format verfügbar: {str(e)}") from e
                elif "read timed out" in str(e).lower() or "connection reset" in str(e).lower():
                    logger.warning(f"Netzwerkfehler beim Download: {str(e)}. Versuche es erneut...")
                    pass
                else:
                    raise DownloadError(f"yt-dlp Fehler: {str(e)}", code="YT_DLP_ERROR") from e

            except Exception as e:
                last_exception = e
                logger.error(f"Allgemeiner Download-Fehler in Versuch {attempt+1}: {str(e)}", exc_info=True)
                if attempt == max_retries - 1:
                    await self.update.message.reply_text(
                        "❌ Download nach mehreren Versuchen fehlgeschlagen"
                    )
                    break
                backoff_time = 2 ** (attempt + 1)
                logger.info(f"Warte {backoff_time}s vor dem nächsten Versuch")
                await asyncio.sleep(backoff_time)

        if last_exception:
            raise DownloadError(
                f"Download nach {max_retries} Versuchen fehlgeschlagen: {str(last_exception)}",
                code="RETRY_EXHAUSTED",
            ) from last_exception
        return []

    async def _handle_error(self, error_type: str, context: dict = None) -> None:
        context = context or {}
        message = self.ERROR_MESSAGES.get(error_type, "❌ Unbekannter Fehler")
        try:
            formatted_message = message.format(**context)
        except KeyError:
            formatted_message = message
        logger.error(f"Fehler: {error_type}. Nachricht: {formatted_message}", extra=context)
        if self.update and self.update.message:
            try:
                short_message = (
                    formatted_message[:500] + "..." if len(formatted_message) > 500 else formatted_message
                )
                await self.update.message.reply_text(escape_markdown_v2(short_message), parse_mode="MarkdownV2")
            except Exception as e:
                logger.warning(f"Fehler beim Senden der Fehlernachricht: {str(e)}", exc_info=True)
        else:
            logger.warning("Kein Update-Objekt oder Nachricht für Fehlermeldung verfügbar.")

    async def _process_download_result(self, info: Union[Dict[str, Any], str, None], ydl) -> Union[str, List[str]]:
        logger.debug(f"Starte _process_download_result für Info-Typ: {type(info)}")
        if info is None:
            logger.error("Download-Ergebnis ist None.")
            raise DownloadError("yt-dlp Download lieferte kein Ergebnis zurück.")
        if "entries" in info:
            logger.info(f"Playlist erkannt: {info.get('title')}")
            return await self.playlist_processor.process_playlist(info, ydl)
        else:
            logger.info(f"Einzelner Track erkannt: {info.get('title')}")
            temp_file_path, metadata = await self._process_single_track(info, ydl)
            logger.debug(f"_process_single_track abgeschlossen. Temp-Pfad: {temp_file_path}, Metadaten: {metadata.get('title')}")
            
            final_filename = sanitize_filename(f"{metadata['artist']} - {metadata['title']}")
            final_path = Path(self.config.PROCESSED_DIR) / f"{final_filename}.{self.config.AUDIO_FORMAT}"
            logger.debug(f"Generierter finaler Pfad für Einzeltrack: {final_path}")

            await self.metadata_handler.write_metadata(str(temp_file_path), metadata, str(final_path))
            logger.debug(f"Metadaten für Einzeltrack geschrieben.")
            await self.file_utils.safe_rename(str(temp_file_path), str(final_path))
            logger.info(f"Einzeltrack '{metadata.get('title')}' erfolgreich verarbeitet und verschoben zu: {final_path}")
            return str(final_path)

    async def _process_single_track(self, info: Dict[str, Any], ydl) -> Tuple[Path, Dict[str, Any]]:
        logger.debug(f"🎵 Starte _process_single_track für '{info.get('fulltitle', 'Unbekannt')}'")
        raw_title = info.get("fulltitle", info.get("title", "Unbekannter Titel"))
        raw_artist = info.get("artist", info.get("uploader", "Unbekannter Künstler"))
        logger.debug(f"🔍 Raw Title: {raw_title}, Raw Artist: {raw_artist}")

        playlist_count = info.get("n_entries")
        if playlist_count is None or playlist_count == 1:
            info["is_single"] = True
            logger.debug("📀 Nur ein Track erkannt – markiert als Single")
        else:
            info["is_single"] = False
            logger.debug(f"🎧 Playlist erkannt mit {playlist_count} Einträgen – kein Single")

        cleaned_artist = self.artist_cleaner.clean(raw_artist)
        cleaned_title = TitleCleaner.clean_title(raw_title, cleaned_artist)
        logger.debug(f"✅ Bereinigter Titel: {cleaned_title}, Bereinigter Künstler: {cleaned_artist}")

        metadata = await process_metadata({
            **info,
            "title": cleaned_title,
            "artist": cleaned_artist,
            "is_single": info.get("is_single")
        })
        logger.debug(f"🧠 Erhaltene Metadaten nach process_metadata: {metadata.get('title')}, {metadata.get('artist')}")

        file_path_str = info.get("filepath") or info.get("filename") or info.get("_filename")
        if not file_path_str and info.get("requested_downloads"):
            for dl_info in info["requested_downloads"]:
                file_path_str = dl_info.get("filepath") or dl_info.get("file")
                if file_path_str:
                    break

        if file_path_str:
            temp_file_path = Path(file_path_str)
            logger.debug(f"📁 Temporärer Dateipfad gefunden: {temp_file_path}")
        else:
            error_message = f"❌ Download fehlgeschlagen: Kein gültiger Dateipfad im Info-Dictionary gefunden."
            logger.error(error_message, extra={"info_keys": info.keys(), "webpage_url": info.get('webpage_url')})
            raise FileProcessingError(error_message)

        if not await self.file_utils.verify_file(temp_file_path):
            error_message = f"Heruntergeladene Datei ist ungültig oder existiert nicht: {temp_file_path}"
            logger.error(error_message)
            raise FileProcessingError(error_message)

        return temp_file_path, metadata


# -------------------------------------------------------------
# Öffentliche API
# -------------------------------------------------------------


async def download_audio(url: str, update: Update) -> Union[str, List[str]]:
    """
    Hauptfunktion zum Herunterladen von Audio aus YouTube-URLs.
    Diese Funktion wird von anderen Modulen aufgerufen.

    Args:
        url: YouTube-URL (Video oder Playlist)
        update: Telegram-Update-Objekt für Antworten

    Returns:
        Pfad(e) der heruntergeladenen Datei(en) oder leere Liste bei Fehler
    """
    logger.info(f"Öffentliche API 'download_audio' aufgerufen für URL: {url}")
    downloader = YoutubeDownloader(update)
    return await downloader.download_audio(url)