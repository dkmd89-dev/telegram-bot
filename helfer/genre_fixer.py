# helfer/genre_fixer.py

import logging
from typing import Optional
from klassen.artist_map import ARTIST_GENRE_OVERRIDES, ARTIST_RULES, ARTIST_OVERRIDES
from klassen.clean_artist import CleanArtist

# Setup: Dateibasiertes Logging (optional)
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("GenreFetcher")
logger.setLevel(logging.INFO)

# Optional: Dateilog mit Rotation
if not logger.handlers:
    file_handler = RotatingFileHandler("logs/genre_fixer.log", maxBytes=100_000, backupCount=3)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

class GenreFetcher:
    """Bestimmt das Genre basierend auf Titel und Künstler, mit Logging und Fallback auf Artist-Map."""

    def __init__(self):
        self.artist_genre_map = ARTIST_GENRE_OVERRIDES
        self.cleaner = CleanArtist(artist_rules=ARTIST_RULES, artist_overrides=ARTIST_OVERRIDES)

    async def get_genre(self, title: str, artist: str) -> Optional[str]:
        clean_artist = self.cleaner.clean(artist).lower()
        log_prefix = f"[{artist} – {title}]"

        logger.debug(f"{log_prefix} 🔍 Starte Genre-Erkennung")

        genre = await self.get_genre_from_musicbrainz(title, artist)
        if genre:
            logger.info(f"{log_prefix} ✅ Genre über MusicBrainz: {genre}")
            return genre

        genre = await self.get_genre_from_genius(title, artist)
        if genre:
            logger.info(f"{log_prefix} ✅ Genre über Genius: {genre}")
            return genre

        genre = await self.get_genre_from_lastfm(title, artist)
        if genre:
            logger.info(f"{log_prefix} ✅ Genre über Last.fm: {genre}")
            return genre

        genre = self.artist_genre_map.get(clean_artist)
        if genre:
            logger.info(f"{log_prefix} ℹ️ Fallback-Genre über Artist-Zuordnung: {genre}")
        else:
            logger.warning(f"{log_prefix} ❌ Kein Genre erkennbar")

        return genre

    async def get_genre_from_musicbrainz(self, title: str, artist: str) -> Optional[str]:
        # MusicBrainz-API-Integration hier einbauen
        return None

    async def get_genre_from_genius(self, title: str, artist: str) -> Optional[str]:
        # Genius-API-Integration hier einbauen
        return None

    async def get_genre_from_lastfm(self, title: str, artist: str) -> Optional[str]:
        # Last.fm-API-Integration hier einbauen
        return None