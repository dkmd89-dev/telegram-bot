# -*- coding: utf-8 -*-
#!/usr/bin/env python3
# Standardbibliotheken
import argparse
import hashlib
import logging
import os
import re
import shutil
import sys
import platform
from datetime import datetime
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from logging.handlers import RotatingFileHandler

# Externe AbhÃ¤ngigkeiten
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen import MutagenError

# Lokale Module
from config import Config

# Logging konfigurieren
logger = logging.getLogger(__name__)


def setup_debug_logging():
    debug_log_path = Config.LOG_DIR / "debug.log"
    debug_handler = RotatingFileHandler(
        debug_log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    debug_handler.setFormatter(debug_formatter)
    logging.getLogger().addHandler(debug_handler)
    logging.getLogger().setLevel(logging.DEBUG)


class MusicOrganizer:
    """Intelligente Musikorganisation mit erweiterter KÃ¼nstlererkennung"""

    def __init__(self, source_dir: Optional[Path] = None):
        self.source_dir = source_dir if source_dir else Config.PROCESSED_DIR
        self.target_dir = Config.LIBRARY_DIR
        self.archive_dir = Config.ARCHIVE_DIR
        self.log_dir = Config.LOG_DIR
        self.file_hashes: Set[str] = set()
        self.stats = {"processed": 0, "duplicates": 0, "errors": 0}
        self.error_log: List[str] = []

        # Logging-Setup
        self._setup_logging()

        # Erstelle Zielverzeichnisse falls nicht vorhanden
        self.target_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Erstelle Spezialverzeichnisse
        for special_dir in Config.ORGANIZER_CONFIG["special_dirs"]:
            (self.target_dir / special_dir).mkdir(exist_ok=True)

        # Log-Datei fÃ¼r fehlende Album-Tags
        self.missing_album_log = (
            self.log_dir / Config.ORGANIZER_CONFIG["missing_album_log"]
        )
        if not self.missing_album_log.exists():
            self.missing_album_log.touch()

        # Cache fÃ¼r bereits erstellte Album-Ordner
        self.created_albums: Set[Path] = set()

        # Lade vorhandene Datei-Hashes fÃ¼r DuplikatsprÃ¼fung
        if Config.ORGANIZER_CONFIG["duplicate_check"]:
            self._hashes_initialized = False

    def _setup_logging(self) -> None:
        """Rotierende Log-Dateien mit GrÃ¶Ãenbegrenzung"""
        logging.getLogger().handlers.clear()  # Existierende Handler entfernen

        log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        # Rotierender FileHandler (max. 5 MB pro Datei, 5 Backups)
        file_handler = RotatingFileHandler(
            Config.LOG_DIR / "music_organizer.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(log_formatter)

        # Console-Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)

        logging.basicConfig(
            level=logging.INFO, handlers=[file_handler, console_handler]
        )

    def _reset_stats(self) -> None:
        """Setzt alle Statistiken zurÃ¼ck"""
        self.stats = {"processed": 0, "duplicates": 0, "errors": 0}
        self.error_log = []

    def get_error_samples(self, max_samples: int = 3) -> List[str]:
        """Gibt eine Auswahl von Fehlermeldungen zurÃ¼ck"""
        return self.error_log[:max_samples]

    @property
    def organization_stats(self) -> Dict[str, int]:
        """Gibt aktuelle Statistiken als Dictionary zurÃ¼ck"""
        return self.stats.copy()

    def _load_existing_hashes(self) -> None:
        """LÃ¤dt vorhandene Datei-Hashes fÃ¼r DuplikatsprÃ¼fung"""
        if not self.target_dir.exists():
            return

        logger.info("Lade vorhandene Datei-Hashes fÃ¼r DuplikatsprÃ¼fung...")
        count = 0
        for root, _, files in os.walk(self.target_dir):
            for file in files:
                file_path = Path(root) / file
                try:
                    file_hash = self._calculate_file_hash(file_path)
                    self.file_hashes.add(file_hash)
                    count += 1
                except Exception as e:
                    logger.warning(f"Konnte Hash nicht berechnen fÃ¼r {file_path}: {e}")
        logger.info(f"{count} Datei-Hashes geladen")

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Berechnet MD5-Hash einer Datei fÃ¼r DuplikatsprÃ¼fung"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _is_duplicate(self, file_path: Path) -> bool:
        """Prüft ob Datei bereits im Zielverzeichnis existiert (basierend auf Inhalt)"""
        if not Config.ORGANIZER_CONFIG["duplicate_check"]:
            return False

        if not self._hashes_initialized:
            self._load_existing_hashes()
            self._hashes_initialized = True

        try:
            file_hash = self._calculate_file_hash(file_path)
            if file_hash in self.file_hashes:
                logger.info(f"Duplikat gefunden und übersprungen: {file_path}")
                return True
            return False
        except Exception as e:
            logger.warning(f"Fehler bei Duplikatsprüfung für {file_path}: {e}")
            return False

    def _parse_artist_from_filename(self, filename: str) -> Tuple[str, str]:
        """Erweiterte Regex-Patterns fÃ¼r Dateinamen mit besserer KÃ¼nstlererkennung"""
        filename = Path(filename).stem
        for pattern in Config.ORGANIZER_CONFIG["filename_patterns"]:
            match = re.match(pattern, filename, re.IGNORECASE)
            if match:
                artist = match.group("artist").replace("_", " ").strip()
                title = match.group("title").replace("_", " ").strip()
                if artist and title:
                    return self.clean_artist_name(artist), title
        return Config.ORGANIZER_CONFIG["fallback_artist"], filename

    def _truncate_path(self, path: Path, max_length: int = 200) -> Path:
        """KÃ¼rzt zu lange Pfade fÃ¼r Windows-KompatibilitÃ¤t"""
        if len(str(path)) <= max_length:
            return path

        stem = path.stem[
            : (max_length - len(path.suffix) - 10)
        ]  # Platz fÃ¼r Suffix + Counter
        truncated = path.with_name(f"{stem}_TRUNCATED{path.suffix}")
        logger.warning(f"Pfad gekÃ¼rzt: {path} -> {truncated}")
        return truncated

    def get_audio_metadata(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Extrahiert Metadaten aus Audiodatei mit verbesserter KÃ¼nstlererkennung"""
        try:
            if file_path.suffix.lower() == ".mp3":
                audio = EasyID3(file_path)
            elif file_path.suffix.lower() == ".flac":
                audio = FLAC(file_path)
            elif file_path.suffix.lower() in (".m4a", ".mp4"):
                audio = MP4(file_path)
            elif file_path.suffix.lower() in (".ogg", ".opus"):
                audio = OggOpus(file_path)
            else:
                return None

            return self._parse_metadata(audio, file_path)
        except Exception as e:
            logger.error(f"Metadaten-Lesefehler fÃ¼r {file_path}: {e}")
            # Fallback: Versuche nur aus Dateiname zu parsen
            if Config.ORGANIZER_CONFIG["parse_artist_from_filename"]:
                artist, title = self._parse_artist_from_filename(file_path.name)
                return {
                    "artist": artist,
                    "title": title,
                    "album": Config.METADATA_DEFAULTS["album"],
                    "year": Config.METADATA_DEFAULTS["year"],
                    "tracknumber": Config.METADATA_DEFAULTS["track_number"],
                    "album_artist": artist,
                    "genre": [Config.METADATA_DEFAULTS["genre"]],
                    "album_type": "single",
                    "is_single": True,
                }
            return None

    def _parse_metadata(self, audio: Any, file_path: Path) -> Dict[str, Any]:
        """Verarbeitet Rohmetadaten zu strukturierten Daten"""
        metadata = {
            "artist": self._get_artist(audio, file_path),
            "title": self._get_title(audio, file_path),
            "album": self._get_album(audio),
            "year": self._get_year(audio),
            "tracknumber": self._get_track_number(audio),
            "album_artist": self._get_album_artist(audio),
            "genre": self._get_genre(audio),
            "album_type": self._infer_album_type(audio),
        }

        # Bestimme ob es sich um eine Single handelt
        metadata["is_single"] = self._is_single_track(metadata)

        return metadata

    def _get_artist(self, audio: Any, file_path: Optional[Path] = None) -> str:
        """Verbesserte KÃ¼nstlererkennung mit erweiterten Fallbacks"""
        # Zuerst versuchen, den Artist aus den Metadaten zu holen
        if isinstance(audio, MP4):
            artist = audio.get("\xa9ART", [""])[0]
        else:
            artist = audio.get("artist", [""])[0]
        artist = artist if artist else ""

        # Falls kein Artist gefunden wurde, versuche aus dem Dateinamen zu parsen
        if (
            not artist
            and file_path
            and Config.ORGANIZER_CONFIG["parse_artist_from_filename"]
        ):
            artist, _ = self._parse_artist_from_filename(file_path.name)

        # Bereinige den KÃ¼nstlernamen
        artist = (
            self.clean_artist_name(artist)
            if artist
            else Config.ORGANIZER_CONFIG["fallback_artist"]
        )

        # Playlist-Override falls definiert
        override = Config.ORGANIZER_CONFIG.get("playlist_force_artist")
        if override:
            if (file_path and "playlist" in file_path.stem.lower()) or (
                override.lower() in artist.lower()
            ):
                artist = override

        return artist

    def clean_artist_name(self, artist: str) -> str:
        """Bereinigt KÃ¼nstlernamen radikal - behÃ¤lt nur Artist1 und entfernt alles andere"""
        if not artist:
            return Config.ORGANIZER_CONFIG["fallback_artist"]

        # Originalwert speichern fÃ¼r Fallback
        original_artist = artist.strip()

        # 1. Alles nach Kollaborations-Trennzeichen entfernen
        separators = [
            r"\sfeat\.",
            r"\sft\.",
            r"\swith",
            r"\s&",
            r"\sx",
            r"\s/",
            r"\s\+",
            r"\sVS\.?",
            r"\spresents",
            r"\smeets",
            r"\sund",
            r"\smit",
            r",",
            r";",
        ]

        # Kombiniere alle Trennzeichen
        separator_pattern = "|".join(separators)
        artist = re.split(separator_pattern, artist, flags=re.IGNORECASE)[0].strip()

        # 2. Alles in Klammern entfernen
        artist = re.sub(r"[\(\[{].*?[\)\]}]", "", artist).strip()

        # 3. Sonderzeichen entfernen (auÃer Bindestrichen und Leerzeichen)
        artist = re.sub(r"[^\w\sÃ¤Ã¶Ã¼ÃÃÃÃ\-]", "", artist)

        # 4. Mehrfache Leerzeichen ersetzen
        artist = re.sub(r"\s+", " ", artist).strip()

        # 5. Standardisierung spezieller FÃ¤lle
        artist = re.sub(r"\bThe\s+", "", artist, flags=re.IGNORECASE)
        artist = re.sub(r"\bDJ\b", "", artist, flags=re.IGNORECASE)

        # 6. Wenn leer, Originalwert zurÃ¼ckgeben (bereinigt)
        if not artist:
            artist = re.sub(r"[^\w\sÃ¤Ã¶Ã¼ÃÃÃÃ\-]", "", original_artist)
            artist = re.sub(r"\s+", " ", artist).strip()
            if not artist:  # Falls immer noch leer
                return Config.ORGANIZER_CONFIG["fallback_artist"]

        return artist

    def contains_whitelisted_artist(self, artist_raw: str) -> Optional[str]:
        """PrÃ¼ft auf EXAKTE Artist-Matches (keine Teilstrings)"""
        if not artist_raw:
            return None

        whitelist = [
            a.lower() for a in Config.ORGANIZER_CONFIG.get("filter_artists", [])
        ]

        # 1. Kollaborationen splitten (feat., &, etc.)
        parts = re.split(
            r"\s(?:feat\.|ft\.|with|&|x|\/|\+|vs\.?|presents|meets|und|mit)\s",
            artist_raw,
            flags=re.IGNORECASE,
        )
        parts = [re.sub(r"\([^)]*\)", "", p).strip() for p in parts]

        # 2. Jeden Teil auf EXAKTE Ãbereinstimmung prÃ¼fen (case-insensitive)
        for part in parts:
            part_clean = re.sub(r"[^\w\sÃ¤Ã¶Ã¼ÃÃÃÃ\-]", "", part).strip().lower()

            # Exakter Match (ohne Fuzzy-Logik!)
            if part_clean in whitelist:
                return part_clean

        return None

    def _get_title(self, audio: Any, file_path: Path) -> str:
        """Extrahiert Titel mit Fallback auf Dateinamen-Parsing"""
        # Versuche zuerst aus Metadaten
        if isinstance(audio, MP4):
            title = audio.get("\xa9nam", [""])[0]
        else:
            title = audio.get("title", [""])[0]

        title = title if title else ""

        # Falls kein Titel in Metadaten, versuche aus Dateiname zu parsen
        if not title and Config.ORGANIZER_CONFIG["parse_artist_from_filename"]:
            _, title = self._parse_artist_from_filename(file_path.name)

        return self.sanitize_filename(title) if title else file_path.stem

    def _get_album(self, audio: Any) -> str:
        """Extrahiert Album mit intelligentem Fallback"""
        if isinstance(audio, MP4):
            album = audio.get("\xa9alb", [Config.METADATA_DEFAULTS["album"]])[0]
        else:
            album = audio.get("album", [Config.METADATA_DEFAULTS["album"]])[0]
        return (
            self.sanitize_filename(album)
            if album
            else Config.METADATA_DEFAULTS["album"]
        )

    def _get_year(self, audio: Any) -> str:
        """Extrahiert Jahr mit Validierung"""
        if isinstance(audio, MP4):
            year = audio.get("\xa9day", [Config.METADATA_DEFAULTS["year"]])[0]
        else:
            year = audio.get("date", [Config.METADATA_DEFAULTS["year"]])[0]

        # Extrahiere Jahreszahl falls vorhanden
        match = re.search(r"\d{4}", str(year))
        return match.group(0) if match else Config.METADATA_DEFAULTS["year"]

    def _get_track_number(self, audio: Any) -> str:
        """Extrahiert Tracknummer mit Formatierung"""
        if isinstance(audio, MP4):
            track = (
                str(audio.get("trkn", [(0, 0)])[0][0])
                if "trkn" in audio
                else Config.METADATA_DEFAULTS["track_number"]
            )
        else:
            track = audio.get(
                "tracknumber", [Config.METADATA_DEFAULTS["track_number"]]
            )[0]

        # Bereinige Tracknummer
        track = re.sub(r"\D", "", track.split("/")[0])
        return (
            f"{int(track):02d}"
            if track.isdigit()
            else Config.METADATA_DEFAULTS["track_number"]
        )

    def _get_album_artist(self, audio: Any) -> str:
        """Extrahiert AlbumkÃ¼nstler mit Fallback auf HauptkÃ¼nstler"""
        if isinstance(audio, MP4):
            album_artist = audio.get("aART", [""])[0]
        else:
            album_artist = audio.get("albumartist", [""])[0]

        artist = self._get_artist(audio)
        return self.sanitize_filename(album_artist) if album_artist else artist

    def _get_genre(self, audio: Any) -> List[str]:
        """Extrahiert Genre(s) mit Bereinigung"""
        if isinstance(audio, MP4):
            genre = audio.get("\xa9gen", [Config.METADATA_DEFAULTS["genre"]])
        else:
            genre = audio.get("genre", [Config.METADATA_DEFAULTS["genre"]])

        genres = []
        for g in genre:
            if isinstance(g, str):
                genres.extend(g.split(";"))

        return [self.sanitize_filename(g) for g in genres if g and str(g).strip()]

    def _infer_album_type(self, audio: Any) -> str:
        """Verbesserte Album-Typ-Erkennung mit Compilation-Logik"""
        album_artist = self._get_album_artist(audio).lower()
        album = self._get_album(audio).lower()

        if "various artists" in album_artist or "compilation" in album:
            return "compilation"
        if "single" in album or "ep" in album:
            return "single" if "single" in album else "ep"
        return "album"

    def _is_single_track(self, metadata: Dict[str, Any]) -> bool:
        """Bestimmt ob es sich um einen Single-Track handelt"""
        # Explizite Marker
        if metadata["album_type"] in ["single", "ep"]:
            return True

        # Albumname gleich Titel
        if metadata["album"].lower() == metadata["title"].lower():
            return True

        # Kein Albumname oder "Unknown"
        if (
            not metadata["album"]
            or metadata["album"] == Config.METADATA_DEFAULTS["album"]
        ):
            return True

        # Compilation-Alben
        if metadata["album_type"] == "compilation":
            return True

        return False

    def create_unique_dir(self, base_path: Path) -> Path:
        """Erstellt einen eindeutigen Ordnerpfad falls der Basisordner existiert"""
        if not base_path.exists():
            return base_path
        if any(base_path.glob("*.*")):  # EnthÃ¤lt Dateien?
            return base_path
        counter = 1
        while True:
            new_path = base_path.with_name(f"{base_path.name} ({counter})")
            if not new_path.exists():
                return new_path
            counter += 1

    # services/organizer.py

# ... (unveränderter Code)

    def _get_destination_path(self, metadata: Dict[str, Any], suffix: str) -> Path:
        """Generiert Zielpfad basierend auf Metadaten mit sicheren Zugriffen und Debugging.

        Args:
            metadata (Dict[str, Any]): Ein Wörterbuch mit Metadaten des Tracks.
            suffix (str): Die Dateierweiterung (z.B. '.m4a').

        Returns:
            Path: Der vollständige Zielpfad.
        """
        logger.debug(f"Starte _get_destination_path f\u00FCr Metadaten: {metadata}")

        # Artist und Titel bereinigen
        # Sicherstellen, dass artist existiert, bevor es verwendet wird
        artist_raw = metadata.get("artist", Config.ORGANIZER_CONFIG["fallback_artist"])
        artist = self.sanitize_filename(self.clean_artist_name(artist_raw))
        title = self.sanitize_filename(metadata.get("title", "Unbekannter Titel")) # Sicherer Zugriff

        # Sicherer Zugriff auf Metadaten mit .get() und Standardwerten aus der Config
        year = metadata.get("year", Config.METADATA_DEFAULTS.get("year", "0000"))
        # Sicherstellen, dass year ein String ist, falls es als Integer kommt
        if not isinstance(year, str):
            year = str(year)

        track_num = metadata.get("track_number", Config.METADATA_DEFAULTS.get("track_number", "01"))
        if not isinstance(track_num, str):
            track_num = str(track_num) # Sicherstellen, dass track_num ein String ist

        is_single = metadata.get("is_single", False)
        album = self.sanitize_filename(metadata.get("album", Config.METADATA_DEFAULTS.get("album", "Unknown Album")))

        logger.debug(f"Metadaten f\u00FCr Pfadgenerierung: Artist='{artist}', Title='{title}', Year='{year}', Track='{track_num}', Album='{album}', IsSingle={is_single}")

        if is_single:
            # Für Singles: Artist/Singles/Jahr - Titel.m4a
            dir_format_str = Config.ORGANIZER_CONFIG["single_dir_format"]
            filename_format_str = Config.ORGANIZER_CONFIG["track_filename_format"]

            # Generiere den Unterordnerpfad (z.B. "Singles")
            # Hier sind 'artist', 'album', 'year', 'title', 'tracknumber' als Platzhalter möglich,
            # auch wenn nur "Singles" erwartet wird, ist es gut, alle bereitzustellen.
            relative_dir_path = Path(dir_format_str.format(
                artist=artist,
                album=album, # Stellen Sie sicher, dass album hier verfügbar ist, falls es im dir_format_str verwendet wird
                year=year,
                title=title,
                tracknumber=track_num
            ))
            
            # Generiere den Dateinamen (z.B. "2025 - G.I.N.A.")
            # track_filename_format ist jetzt "{year} - {title}"
            filename = f"{filename_format_str.format(year=year, title=title, tracknumber=track_num)}{suffix}"
            
            # Kombiniere alles: LIBRARY_DIR / Artist / Singles / Jahr - Titel.m4a
            final_path = Config.LIBRARY_DIR / artist / relative_dir_path / filename

        else:
            # Für Album-Tracks: Artist/Jahr - Album/Track - Titel.m4a
            dir_format_str = Config.ORGANIZER_CONFIG["album_dir_format"]
            filename_format_str = Config.ORGANIZER_CONFIG["track_filename_format"] # Oder eine spezifische Album-Track-Formatierung, falls vorhanden

            # Generiere den Album-Ordnerpfad (z.B. "2024 - My Album")
            album_dir_name = dir_format_str.format(
                year=year,
                album=album,
                artist=artist, # Auch hier alle möglichen Platzhalter übergeben
                title=title,
                tracknumber=track_num
            )
            album_base_path = Config.LIBRARY_DIR / artist / "Albums" / album_dir_name
            final_album_path = self.create_unique_dir(album_base_path)
            
            # Generiere den Dateinamen (z.B. "01 - My Song")
            filename = f"{filename_format_str.format(tracknumber=track_num, title=title, year=year)}{suffix}"
            
            # Kombiniere alles: LIBRARY_DIR / Artist / Albums / Jahr - Album / Track - Titel.m4a
            final_path = final_album_path / filename

        # Stelle sicher, dass das Zielverzeichnis existiert
        final_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Generierter Zielpfad: {final_path}")
        return final_path

    def _archive_file(self, file_path: Path) -> None:
        """Verschiebt eine erfolgreich kopierte Datei ins Archiv"""
        if not Config.ORGANIZER_CONFIG["archive_processed"]:
            return
        try:
            archive_path = self.archive_dir / file_path.name
            if archive_path.exists():
                # Falls Datei bereits existiert, einen eindeutigen Namen erstellen
                counter = 1
                while archive_path.exists():
                    archive_path = (
                        self.archive_dir
                        / f"{file_path.stem} ({counter}){file_path.suffix}"
                    )
                    counter += 1
            shutil.move(str(file_path), str(archive_path))
        except Exception as e:
            logging.error(f"Fehler beim Archivieren von {file_path.name}: {e}")

    def _process_file(self, file_path: Path) -> None:
        """Verarbeitet eine einzelne Datei mit Fehlerklassen-Differenzierung"""
        try:
            if (
                not file_path.is_file()
                or file_path.suffix.lower() not in Config.SUPPORTED_FORMATS
            ):
                return

            # PfadlÃ¤ngen-Check (speziell fÃ¼r Windows)
            if platform.system() == "Windows" and len(str(file_path)) > 200:
                file_path = self._truncate_path(file_path, max_length=200)

            if self._is_duplicate(file_path):
                self.stats["duplicates"] += 1
                return

            metadata = self.get_audio_metadata(file_path)
            if not metadata:
                logger.warning(f"Metadaten konnten nicht gelesen werden: {file_path}")
                self.stats["errors"] += 1
                self.error_log.append(
                    f"{file_path.name}: Metadaten konnten nicht gelesen werden"
                )
                return

            # Nur bestimmte Artists verarbeiten (aus Config)
            if not self.contains_whitelisted_artist(metadata["artist"]):
                logger.info(
                    f"Ãbersprungen (kein erlaubter Artist in '{metadata['artist']}'): {file_path}"
                )
                return

            # Generiere Zielpfad
            dest_path = self._get_destination_path(metadata, file_path.suffix)

            # Erstelle das Verzeichnis falls nÃ¶tig
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Behandle Namenskonflikte
            if dest_path.exists():
                # Wenn die existierende Datei identisch ist, behandeln wir sie als Duplikat
                if self._calculate_file_hash(file_path) == self._calculate_file_hash(
                    dest_path
                ):
                    logger.info(f"Duplikat gefunden und Ã¼bersprungen: {file_path}")
                    self.stats["duplicates"] += 1
                    return

                # Andernfalls einen eindeutigen Namen erstellen
                base = dest_path.stem
                suffix = dest_path.suffix
                counter = 1
                while dest_path.exists():
                    dest_path = dest_path.with_name(f"{base} ({counter}){suffix}")
                    counter += 1

            # Kopiere Datei (behalte Metadaten mit copy2)
            shutil.copy2(file_path, dest_path)

            # FÃ¼ge Hash der neuen Datei hinzu
            file_hash = self._calculate_file_hash(dest_path)
            self.file_hashes.add(file_hash)
            self.stats["processed"] += 1
            logger.info(f"Kopiert: {file_path} -> {dest_path}")

            # Verschiebe Original ins Archiv
            self._archive_file(file_path)

        except (OSError, shutil.Error) as e:
            self.stats["errors"] += 1
            error_msg = f"Dateisystemfehler: {file_path.name} ({str(e)[:100]})"
            self.error_log.append(error_msg)
            logger.error(error_msg)
        except MutagenError as e:
            self.stats["errors"] += 1
            error_msg = f"Metadaten-Fehler: {file_path.name} ({str(e)[:100]})"
            self.error_log.append(error_msg)
            logger.warning(error_msg)
        except Exception as e:
            self.stats["errors"] += 1
            error_msg = f"Kritischer Fehler: {file_path.name} ({str(e)[:100]})"
            self.error_log.append(error_msg)
            logger.critical(error_msg, exc_info=True)

    def _get_new_artists(self) -> Set[str]:
        """Ermittelt neu hinzugefÃ¼gte KÃ¼nstler"""
        current_artists = set()
        # Sammle alle KÃ¼nstlerordner im Zielverzeichnis
        for item in self.target_dir.iterdir():
            if (
                item.is_dir()
                and item.name not in Config.ORGANIZER_CONFIG["special_dirs"]
            ):
                current_artists.add(item.name)
        return current_artists

    def _get_new_albums(self) -> Set[Path]:
        """Ermittelt neu hinzugefÃ¼gte Alben"""
        return self.created_albums

    def organize_files(self) -> Dict[str, int]:
        """Gibt erweiterte Statistiken zurÃ¼ck"""
        self._reset_stats()
        logger.info(f"Starte Verarbeitung von: {self.source_dir}")

        # Durchsuche rekursiv alle unterstÃ¼tzten Dateien im Quellverzeichnis
        for file_path in self.source_dir.rglob("*"):
            self._process_file(file_path)

        logger.info(
            f"Verarbeitung abgeschlossen. {self.stats['processed']} Dateien kopiert, "
            f"{self.stats['duplicates']} Duplikate Ã¼bersprungen, "
            f"{self.stats['errors']} Fehler aufgetreten."
        )

        return {
            "processed": self.stats["processed"],
            "duplicates": self.stats["duplicates"],
            "errors": self.stats["errors"],
            "new_artists": len(self._get_new_artists()),
            "new_albums": len(self._get_new_albums()),
        }

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Bereinigt Dateinamen von ungÃ¼ltigen Zeichen"""
        if not name:
            return "Unknown"

        # Entferne ungÃ¼ltige Zeichen
        for char in Config.ORGANIZER_CONFIG["filename_sanitize_chars"]:
            name = name.replace(char, "_")

        # Entferne Ã¼berschÃ¼ssige Leerzeichen
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _get_artist_folder(self, artist: str) -> Path:
        """Hilfsmethode fÃ¼r einfache Organisation"""
        artist = "Unknown" if not artist else artist
        folder = self.target_dir / artist.replace(" ", "_")
        folder.mkdir(exist_ok=True)
        return folder

    def simple_organize_files(self) -> None:
        """Einfache Organisationsmethode"""
        self._reset_stats()
        logger.info(f"Starte einfache Verarbeitung von: {self.source_dir}")

        for file in self.source_dir.glob(f"*.{Config.AUDIO_FORMAT}"):
            try:
                audio = mutagen.File(file)
                artist = audio.get("artist", ["Unknown"])[0]
                dest = self._get_artist_folder(artist) / file.name
                shutil.move(str(file), str(dest))
                self.stats["processed"] += 1
                logger.info(f"Verschoben: {file} -> {dest}")
            except Exception as e:
                self.stats["errors"] += 1
                error_msg = f"Fehler bei {file.name}: {str(e)}"
                self.error_log.append(error_msg)
                logger.error(error_msg)
                continue

        logger.info(
            f"Einfache Verarbeitung abgeschlossen. {self.stats['processed']} Dateien verschoben, "
            f"{self.stats['errors']} Fehler aufgetreten."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Organisiere Musikdateien")
    parser.add_argument(
        "--source", type=Path, help="Quellverzeichnis (Standard: aus Config)"
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Verwende einfache Organisationsmethode",
    )
    args = parser.parse_args()

    organizer = MusicOrganizer(source_dir=args.source)
    if args.simple:
        organizer.simple_organize_files()
    else:
        organizer.organize_files()
