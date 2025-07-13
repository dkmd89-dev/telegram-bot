import asyncio
from datetime import datetime
from typing import Optional, Dict
from mutagen.mp4 import MP4
import aiohttp

from config import Config
from klassen.title_cleaner import TitleCleaner
from klassen.clean_artist import CleanArtist
from fixes.metadata_fallbacks import fix_metadata_fallbacks
from klassen.artist_map import ARTIST_RULES, ARTIST_OVERRIDES
from utils import sanitize_filename, identify_album_from_video, safe_rename
from logger import log_error, log_debug, log_warning, log_info
from klassen.musicbrainz_client import MusicBrainzClient
from klassen.genius_client import GeniusClient
from klassen.lastfm_client import LastFMClient
from klassen.cover_fixer import CoverFixer
from helfer.lastfm_helpers import pick_best_genre

# Initialisierungen
artist_cleaner = CleanArtist()  # Keine Parameter nötig!e
musicbrainz_client = MusicBrainzClient(artist_cleaner)
genius_client = GeniusClient(artist_cleaner)
lastfm_client = LastFMClient()
cover_fixer = CoverFixer(musicbrainz_client, genius_client, lastfm_client)

class MetadataError(Exception):
    """Custom exception for metadata errors."""
    pass

def process_artist_name(name: str, cleaner: CleanArtist) -> str:
    """Clean and process an artist name."""
    if not name:
        return "Various Artists"
    cleaned_name = cleaner.clean(name)
    processed_name = sanitize_filename(cleaned_name.split("&")[0].split(",")[0].strip())
    return processed_name or "Various Artists"

async def process_metadata(info: dict) -> dict:
    """Process and merge metadata from all sources."""
    if not info.get("title") or not info.get("uploader"):
        log_warning("Invalid metadata received.", {"info": info})
        return Config.METADATA_DEFAULTS.copy()

    video_title = info.get("title", "")
    original_uploader = info.get("uploader", "")
    
    if ' - ' in video_title:
        potential_artist, potential_title = video_title.split(' - ', 1)
        if potential_artist.lower() in original_uploader.lower() or original_uploader.lower() in potential_artist.lower():
            raw_artist = artist_cleaner.clean(potential_artist)
            raw_title = TitleCleaner.clean_title(potential_title)
        else:
            raw_artist = artist_cleaner.clean(original_uploader)
            raw_title = TitleCleaner.clean_title(video_title)
    else:
        raw_artist = artist_cleaner.clean(original_uploader)
        raw_title = TitleCleaner.clean_title(video_title)

    log_info(f"🔍 Starte Metadaten-Verarbeitung für: '{raw_artist}' - '{raw_title}'")

    tasks = {
        "musicbrainz": musicbrainz_client.fetch_metadata(raw_title, raw_artist),
        "genius": genius_client.fetch_metadata(raw_title, raw_artist),
        "lastfm": lastfm_client.fetch_metadata(raw_title, raw_artist)
    }
    
    results = await asyncio.gather(*tasks.values())
    data = dict(zip(tasks.keys(), results))
    
    musicbrainz_data = data.get("musicbrainz", {})
    genius_data = data.get("genius", {})
    lastfm_data = data.get("lastfm", {})

    log_debug("📊 Metadata-Quellen Ergebnisse:", data)

    artist_name = musicbrainz_data.get("artist") or raw_artist
    artist_name = process_artist_name(artist_name, artist_cleaner)

    final_title = musicbrainz_data.get("title") or genius_data.get("title") or raw_title
    final_title = TitleCleaner.clean_title(final_title, artist=artist_name)

    album_name = musicbrainz_data.get("album") or genius_data.get("album") or lastfm_data.get("album") or "Single"
    track_number = musicbrainz_data.get("track_number") or genius_data.get("track_number") or 1
    year = musicbrainz_data.get("year") or genius_data.get("year") or str(datetime.now().year)

    # Genre bestimmen
    raw_genres = (lastfm_data.get("tags", []) + 
                  musicbrainz_data.get("tags", []) + 
                  ([genius_data["genre"]] if genius_data.get("genre") else []))
    genre = pick_best_genre(raw_genres) or Config.METADATA_DEFAULTS["genre"]

    # Cover-Daten abrufen
    cover_data = await cover_fixer.fetch_cover(final_title, artist_name, album_name)

    # 🔠 Lyrics mit Fallback und Mindestlänge
    lyrics = genius_data.get("lyrics", "")
    if not lyrics or len(lyrics.strip()) < 100:
        fallback_lyrics = lastfm_data.get("wiki", "")
        if fallback_lyrics and len(fallback_lyrics.strip()) >= 100:
            log_info(f"📜 Fallback: Lyrics aus Last.fm-Wiki verwendet für '{final_title}'")
            lyrics = fallback_lyrics
        else:
            log_warning(f"⚠️ Keine sinnvollen Lyrics gefunden für '{final_title}'")

    final_metadata = {
        "title": final_title,
        "artist": artist_name,
        "album": album_name,
        "year": year,
        "genre": genre,
        "track_number": track_number,
        "album_artist": musicbrainz_data.get("album_artist") or artist_name,
        "lyrics": lyrics,
        "cover_data": cover_data,
        "tags": list(set(raw_genres))
    }

    final_metadata = fix_metadata_fallbacks(final_metadata, info)
    log_info(f"✅ Metadaten-Verarbeitung abgeschlossen für '{final_metadata['title']}'")
    return final_metadata

async def write_metadata(src_path: str, metadata: dict, dest_path: str):
    """Write metadata to an audio file."""
    log_info(f"📥 Schreibe Metadaten für Datei: '{src_path}'")
    try:
        audio = MP4(src_path)
        audio["\xa9nam"] = metadata.get("title", "Unknown Title")
        audio["\xa9ART"] = metadata.get("artist", "Unknown Artist")
        audio["\xa9alb"] = metadata.get("album", "Unknown Album")
        audio["\xa9day"] = str(metadata.get("year", datetime.now().year))
        audio["\xa9gen"] = metadata.get("genre", "Other")
        audio["aART"] = metadata.get("album_artist", metadata.get("artist"))
        audio["trkn"] = [(metadata.get("track_number", 1), 0)]

        # Lyrics speichern, wenn gültig
        lyrics_text = metadata.get("lyrics", "").strip()
        if lyrics_text and len(lyrics_text) >= 100:
            audio["\xa9lyr"] = lyrics_text
            log_debug(f"📝 Lyrics gespeichert (Länge: {len(lyrics_text)} Zeichen)")
        elif lyrics_text:
            log_info(f"ℹ️ Lyrics zu kurz – nicht gespeichert ({len(lyrics_text)} Zeichen)")
        else:
            log_debug("ℹ️ Keine Lyrics vorhanden zum Schreiben")

        # Cover einbetten, falls vorhanden
        if metadata.get("cover_data"):
            cover_fixer.embed_cover(audio, metadata["cover_data"])

        audio.save()
        await safe_rename(src_path, dest_path)
        log_info(f"📁 Datei erfolgreich umbenannt und gespeichert: '{dest_path}'")
    except Exception as e:
        log_error(f"❌ Fehler beim Schreiben der Metadaten für {src_path}: {str(e)}", exc_info=True)
        raise MetadataError(f"Fehler beim Schreiben der Metadaten: {str(e)}")
