# -*- coding: utf-8 -*-
"""
genre_helfer.py

Dieses Modul ist eine Sammlung von Hilfsfunktionen für die Verwaltung von Musikdateien.
Es kombiniert Funktionalitäten aus verschiedenen Skripten, um Metadaten zu extrahieren,
Genres von externen APIs abzurufen, Coverbilder zu finden und Metadaten in M4A-Dateien
zu schreiben. Es enthält auch Werkzeuge zur Interaktion mit einer Navidrome-Instanz.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Union, Optional, List, Dict, Any, Tuple
from config import Config
from logger import log_warning, log_error

import requests
from mutagen.mp4 import MP4, MP4Cover

# Annahme: Diese Module sind Teil deines Projekts
# Du musst sicherstellen, dass die Importpfade korrekt sind.

from helfer.genre_map import normalize_genre, get_genre_stats
from helfer.yt_utils import get_youtube_thumbnail
from api.navidrome_api import NavidromeAPI
from klassen.musicbrainz_client import MusicBrainzClient
from klassen.genius_client import GeniusClient
from klassen.lastfm_client import LastFMClient
#from metadata import (
#    fetch_genius_metadata,
#)

# --- Globale Konfigurationen ---
# Ein Semaphore, um die Anzahl paralleler API-Anfragen zu begrenzen
API_SEMAPHORE = asyncio.Semaphore(5)

# Ein einfacher Cache für bereits gefundene Genres von Künstlern
ARTIST_GENRE_CACHE: Dict[str, str] = {}


# --- Logging-Setup ---

def setup_logger(name: str, log_file: str, level: int = logging.INFO) -> logging.Logger:
    """
    Richtet einen Logger mit einem spezifischen Namen und einer Log-Datei ein.
    
    Args:
        name (str): Der Name des Loggers.
        log_file (str): Der Pfad zur Log-Datei.
        level (int): Das Logging-Level (z.B. logging.INFO).

    Returns:
        logging.Logger: Das konfigurierte Logger-Objekt.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Entfernt vorhandene Handler, um doppeltes Logging zu vermeiden
    if logger.hasHandlers():
        logger.handlers.clear()

    # Stellt sicher, dass das Log-Verzeichnis existiert
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    # Erstellt einen File-Handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    return logger

# Beispiel für einen Standard-Logger, der in diesem Modul verwendet wird
logger = setup_logger("genre_helfer", Config.LOG_DIR / "genre.log")


# --- Metadaten-Extraktion (M4A) ---

def get_tags_from_file(file_path: Path) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extrahiert Künstler, Album und Titel aus einer M4A-Datei.

    Args:
        file_path (Path): Der Pfad zur Musikdatei.

    Returns:
        Tuple[Optional[str], Optional[str], Optional[str]]: Ein Tupel mit (Künstler, Album, Titel).
    """
    try:
        audio = MP4(file_path)
        if not audio.tags:
            logger.warning(f"Keine Tags in Datei gefunden: {file_path.name}")
            return None, None, None

        artist = audio.tags.get("\xa9ART", [None])[0]
        album = audio.tags.get("\xa9alb", [None])[0]
        title = audio.tags.get("\xa9nam", [None])[0]
        
        return str(artist).strip() if artist else None, \
               str(album).strip() if album else None, \
               str(title).strip() if title else None
    except Exception as e:
        logger.error(f"Fehler beim Lesen der Tags aus {file_path.name}: {e}")
        return None, None, None


# --- Genre-Abruf von externen APIs ---

def get_genre_by_artist_name(artist_name: str) -> Optional[str]:
    try:
        # Lazy import! ❗ Verhindert Circular Import mit metadata.py
        from metadata import fetch_musicbrainz_metadata

        data = fetch_musicbrainz_metadata(artist_name=artist_name, search_album=False)
        if data and "genre" in data and data["genre"]:
            genre = data["genre"]
            logger.debug(f"🎧 Genre über MusicBrainz gefunden: {genre}")
            return genre
        else:
            logger.debug(f"🕵️ Kein Genre über MusicBrainz für '{artist_name}' gefunden.")
    except Exception as e:
        logger.error(f"❌ Fehler beim Abrufen von MusicBrainz-Genre für '{artist_name}': {e}")
    return None


def get_tags_from_lastfm(artist_name: str) -> Optional[list[str]]:
    try:
        # Wieder: Lazy import für fetch_lastfm_metadata
        from metadata import fetch_lastfm_metadata

        data = fetch_lastfm_metadata(artist_name)
        tags = data.get("tags") if data else []
        logger.debug(f"🏷️ Tags von Last.fm für {artist_name}: {tags}")
        return tags
    except Exception as e:
        logger.error(f"❌ Fehler beim Abrufen von Last.fm-Tags: {e}")
        return []


def get_musicbrainz_genre_by_artist(artist_name: str) -> Optional[str]:
    """
    Holt das Genre für einen Künstler über MusicBrainz.
    """
    import time
    import urllib.parse

    # Suche nach Artist-ID
    query = urllib.parse.quote(artist_name)
    search_url = f"https://musicbrainz.org/ws/2/artist/?query=artist:{query}&fmt=json"
    headers = {
        "User-Agent": "yt-music-bot/1.0 (https://github.com/yourrepo)",
    }

    response = requests.get(search_url, headers=headers, timeout=10)
    response.raise_for_status()
    results = response.json().get("artists", [])

    if not results:
        return None

    artist_id = results[0]["id"]

    # Kleine Wartezeit wegen Rate Limit
    time.sleep(1)

    # Hole Artist-Details
    detail_url = f"https://musicbrainz.org/ws/2/artist/{artist_id}?inc=genres&fmt=json"
    detail_response = requests.get(detail_url, headers=headers, timeout=10)
    detail_response.raise_for_status()

    genres = detail_response.json().get("genres", [])
    if genres:
        return genres[0]["name"].lower()

    return None

async def fetch_genre_from_apis(title: str, artist: str) -> str:
    """
    Ruft Genre-Informationen von aktivierten externen APIs ab und normalisiert sie.
    Verwendet einen Semaphore, um die Anzahl gleichzeitiger Anfragen zu steuern.

    Args:
        title (str): Der Titel des Songs.
        artist (str): Der Künstler des Songs.

    Returns:
        str: Das normalisierte Genre oder ein leerer String, wenn keins gefunden wurde.
    """
    if not title or not artist:
        logger.debug(f"Titel oder Künstler fehlen für Genre-Suche.")
        return ""

    # Prüfen, ob für diesen Künstler bereits ein Genre im Cache ist
    if artist in ARTIST_GENRE_CACHE:
        cached_genre = ARTIST_GENRE_CACHE[artist]
        logger.debug(f"Genre für '{artist}' aus Cache geladen: '{cached_genre}'")
        return cached_genre

    logger.info(f"🔍 Starte Genre-Suche für: {artist} – {title}")
    
    async with API_SEMAPHORE:
        tasks = []
        api_names = [] # Um die API-Namen den Ergebnissen zuzuordnen

        if Config.MUSICBRAINZ_ENABLED:
            tasks.append(fetch_musicbrainz_metadata(title, artist))
            api_names.append("MusicBrainz")
            logger.debug("MusicBrainz API für Genre-Suche aktiviert.")
        if Config.GENIUS_ENABLED:
            tasks.append(fetch_genius_metadata(title, artist))
            api_names.append("Genius")
            logger.debug("Genius API für Genre-Suche aktiviert.")
        if Config.LASTFM_ENABLED:
            tasks.append(fetch_lastfm_metadata(title, artist))
            api_names.append("Last.fm")
            logger.debug("Last.fm API für Genre-Suche aktiviert.")

        if not tasks:
            logger.warning("⚠️ Keine Genre-Quellen (APIs) aktiviert in der Konfiguration!")
            return ""

        results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f"API-Abfrage Ergebnisse (roh) für '{artist} – {title}': {results}")

        direct_genres: List[str] = []
        all_tags: List[str] = []

        for i, result in enumerate(results):
            api_name = api_names[i]
            if isinstance(result, Exception):
                logger.warning(f"Fehler bei {api_name}-API-Abfrage für '{artist} – {title}': {result}")
                continue
            
            if result:
                logger.debug(f"Rohdaten von {api_name} für '{artist} – {title}': {result}")
                
                if result.get("genre"):
                    genre_val = result["genre"]
                    if isinstance(genre_val, list):
                        direct_genres.extend(genre_val)
                        logger.debug(f"Direkte Genres von {api_name} (Liste): {genre_val}")
                    else:
                        direct_genres.append(genre_val)
                        logger.debug(f"Direktes Genre von {api_name} (String): '{genre_val}'")
                
                if result.get("tags"):
                    all_tags.extend(result["tags"])
                    logger.debug(f"Tags von {api_name}: {result['tags']}")
        
        # 1. Priorität: Direkte Genre-Informationen verarbeiten
        if direct_genres:
            logger.debug(f"Verarbeite direkte Genres: {direct_genres}")
            for raw_genre in direct_genres:
                normalized = normalize_genre(raw_genre)
                logger.debug(f"Roh-Genre: '{raw_genre}', Normalisiert: '{normalized}'")
                if normalized:
                    logger.info(f"✅ Genre gefunden (direkt): '{normalized}' für '{artist} – {title}'")
                    ARTIST_GENRE_CACHE[artist] = normalized  # Im Cache speichern
                    return normalized
        else:
            logger.debug("Keine direkten Genres von APIs erhalten.")


        # 2. Priorität: Tags durchsuchen
        if all_tags:
            logger.debug(f"Verarbeite Tags: {all_tags}")
            for tag in all_tags:
                normalized = normalize_genre(tag)
                logger.debug(f"Roh-Tag: '{tag}', Normalisiert: '{normalized}'")
                if normalized:
                    logger.info(f"✅ Genre gefunden (aus Tag): '{normalized}' für '{artist} – {title}'")
                    ARTIST_GENRE_CACHE[artist] = normalized  # Im Cache speichern
                    return normalized
        else:
            logger.debug("Keine Tags von APIs erhalten.")
        
        logger.info(f"❌ Kein gültiges Genre für '{artist} – {title}' gefunden nach API-Abfrage und Normalisierung.")
        return ""


# --- Metadaten in Dateien schreiben ---

def write_genre_to_file(file_path: Path, genre: str) -> bool:
    """
    Schreibt das angegebene Genre in das '\xa9gen'-Tag einer M4A-Datei.

    Args:
        file_path (Path): Der Pfad zur Datei.
        genre (str): Das zu schreibende Genre.

    Returns:
        bool: True bei Erfolg, andernfalls False.
    """
    if not genre:
        return False
    try:
        audio = MP4(file_path)
        audio["\xa9gen"] = [genre]
        audio.save()
        logger.info(f"📝 Genre '{genre}' in {file_path.name} geschrieben.")
        return True
    except Exception as e:
        logger.error(f"❌ Fehler beim Schreiben des Genres in {file_path.name}: {e}")
        return False


# --- Cover-Verarbeitung ---

def has_cover(file_path: Path) -> bool:
    """Prüft, ob eine M4A-Datei bereits ein Cover im 'covr'-Tag hat."""
    try:
        audio = MP4(file_path)
        return 'covr' in audio and bool(audio['covr'])
    except Exception as e:
        logger.warning(f"Fehler beim Prüfen des Covers für {file_path.name}: {e}")
        return False # Im Zweifel lieber von einem Fehler ausgehen


def fetch_cover_from_musicbrainz(artist: str, album: str) -> Optional[bytes]:
    """Sucht nach einem Album-Cover über die MusicBrainz- und Cover Art Archive-API."""
    # Diese Funktion muss implementiert werden. Hier ein Platzhalter.
    logger.info(f"Suche Cover für '{album}' von '{artist}' auf MusicBrainz...")
    # Deine Logik zum Abrufen von MusicBrainz-Daten hier...
    # z.B. mit musicbrainzngs
    return None


def fetch_cover_from_youtube(title: str, artist: str) -> Optional[bytes]:
    """Holt ein Thumbnail von YouTube als Fallback-Cover."""
    logger.info(f"Suche Fallback-Cover für '{title}' auf YouTube...")
    try:
        thumbnail_url = get_youtube_thumbnail(f"{artist} {title}")
        if thumbnail_url:
            response = requests.get(thumbnail_url)
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des YouTube-Thumbnails: {e}")
    return None
    

def embed_cover_to_file(file_path: Path, image_data: bytes) -> bool:
    """Bettet ein Coverbild in eine M4A-Datei ein."""
    try:
        audio = MP4(file_path)
        cover = MP4Cover(image_data, imageformat=MP4Cover.FORMAT_JPEG)
        audio["covr"] = [cover]
        audio.save()
        logger.info(f"🖼️ Cover erfolgreich in {file_path.name} eingebettet.")
        return True
    except Exception as e:
        logger.error(f"❌ Fehler beim Einbetten des Covers in {file_path.name}: {e}")
        return False


# --- Navidrome-Integration ---

def get_navidrome_genres(sort_by: str = "songs", min_songs: int = 0, limit: Optional[int] = None) -> Union[List[Dict[str, Any]], str]:
    """
    Holt, filtert und sortiert Genres von der Navidrome-API.

    Args:
        sort_by (str): Sortierschlüssel ("songs" oder "name").
        min_songs (int): Mindestanzahl an Songs, die ein Genre haben muss.
        limit (Optional[int]): Limitiert die Ausgabe auf die Top-N-Ergebnisse.

    Returns:
        Union[List[Dict[str, Any]], str]: Eine Liste von Genre-Wörterbüchern oder eine Fehlermeldung.
    """
    try:
        # Annahme: NavidromeAPI ist so konfiguriert, dass sie direkt aufgerufen werden kann.
        response = NavidromeAPI.make_request("getGenres")

        if not response or response.get("status") != "ok":
            error_msg = response.get('error', {}).get('message', 'Unbekannter API-Fehler')
            return f"⚠️ Navidrome API-Fehler: {error_msg}"

        genres = response.get("genres", {}).get("genre", [])
        if not genres:
            return "Keine Genres in Navidrome gefunden."

        # Filter- und Sortierlogik
        if min_songs > 0:
            genres = [g for g in genres if g.get("songCount", 0) >= min_songs]
        
        sort_key = lambda g: g.get("songCount", 0) if sort_by == "songs" else g.get("value", "").lower()
        genres.sort(key=sort_key, reverse=(sort_by == "songs"))
        
        if limit is not None and limit > 0:
            genres = genres[:limit]
            
        return genres

    except Exception as e:
        return f"⚠️ Unerwarteter Fehler bei der Abfrage von Navidrome: {str(e)}"

# --- NEUE FUNKTION FÜR DAS FIXEN VON GENRES ---
async def process_all_navidrome_songs_for_genre_fixing():
    """
    Durchläuft alle Songs in Navidrome, um Genres zu verarbeiten,
    und verwendet Künstler-Genres als Fallback.
    Aktualisiert die globalen genre_stats in genre_map.py.
    """
    logger.info("Starte Verarbeitung aller Navidrome-Songs für Genre-Fixing...")
    try:
        all_albums_response = await NavidromeAPI.make_request("getAlbumList2", {"type": "alphabeticalByArtist", "size": "all"})
        if not all_albums_response or all_albums_response.get("status") != "ok":
            logger.error("Fehler beim Abrufen der Alben von Navidrome.")
            return

        albums = all_albums_response.get("albumList2", {}).get("album", [])

        for album in albums:
            album_id = album.get("id")
            album_name = album.get("name", "Unbekanntes Album")
            artist_id = album.get("artistId")

            artist_genre = ""
            if artist_id:
                artist_data_response = await NavidromeAPI.make_request("getArtist", {"id": artist_id})
                if artist_data_response and artist_data_response.get("status") == "ok":
                    artist_genre = artist_data_response.get("artist", {}).get("genre", "")
                else:
                    logger.warning(f"Konnte Künstler-Genre für Artist ID '{artist_id}' nicht abrufen.")


            songs_in_album_response = await NavidromeAPI.make_request("getSongs", {"albumId": album_id})
            if not songs_in_album_response or songs_in_album_response.get("status") != "ok":
                logger.warning(f"Fehler beim Abrufen von Songs für Album '{album_name}'.")
                continue

            songs = songs_in_album_response.get("directory", {}).get("song", [])

            for song in songs:
                song_title = song.get("title", "Unbekannter Titel")
                song_genre = song.get("genre", "") 
                song_path_relativ = song.get("path") # Dies ist der Pfad relativ zur Navidrome-Bibliothek

                # Hier wird die verbesserte normalize_genre Funktion aufgerufen
                final_normalized_genre = normalize_genre(raw_song_genre=song_genre, artist_genre=artist_genre)

                # NEU: Implementierung des TODO-Abschnitts
                if final_normalized_genre: # Nur schreiben, wenn ein gültiges Genre gefunden wurde
                    # Annahme: Config.LIBRARY_DIR ist der Basis-Pfad zu deiner Musikbibliothek
                    # Und song_path_relativ ist der Pfad relativ zu dieser Basis.
                    local_file_path = Path(Config.LIBRARY_DIR) / song_path_relativ
                    
                    if local_file_path.exists() and local_file_path.is_file():
                        current_artist, _, current_title = get_tags_from_file(local_file_path)
                        current_genre_tag = MP4(local_file_path).tags.get("\xa9gen", [""])[0]

                        # Überprüfe, ob das Genre im Tag bereits dem gewünschten Genre entspricht
                        # Dies vermeidet unnötige Schreibvorgänge
                        if normalize_genre(raw_genre=current_genre_tag) != final_normalized_genre:
                            logger.info(f"💾 Aktualisiere Genre für '{song_title}' zu '{final_normalized_genre}' in {local_file_path.name}")
                            write_genre_to_file(local_file_path, final_normalized_genre)
                        else:
                            logger.debug(f"ℹ️ Genre für '{song_title}' ist bereits korrekt '{final_normalized_genre}' in {local_file_path.name}")
                    else:
                        logger.warning(f"Datei '{local_file_path}' für '{song_title}' nicht lokal gefunden. Kann Genre nicht schreiben.")
                else:
                    logger.info(f"Verarbeitet: '{song_title}' (Song-Genre: '{song_genre}', Künstler-Genre: '{artist_genre}') -> Finales Genre: '{final_normalized_genre}' (Kein gültiges Genre zum Schreiben gefunden)")

    except Exception as e:
        logger.error(f"Fehler bei der Genre-Verarbeitung für Navidrome-Songs: {e}", exc_info=True)

    logger.info("Genre-Verarbeitung für Navidrome-Songs abgeschlossen.")
    logger.info(get_genre_stats(as_text=True))