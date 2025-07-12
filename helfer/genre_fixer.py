# helfer/genre_fixer.py

import logging
from typing import Optional
from klassen.artist_map import ARTIST_GENRE_OVERRIDES
from klassen.clean_artist import CleanArtist

logger = logging.getLogger("GenreFetcher")

class GenreFetcher:
    """Bestimmt das Genre basierend auf Titel und K��nstler, mit Logging und Fallback auf Artist-Map."""

    def __init__(self):
        self.artist_genre_map = ARTIST_GENRE_OVERRIDES
        self.cleaner = CleanArtist()

    async def get_genre(self, title: str, artist: str) -> Optional[str]:
        clean_artist = self.cleaner.clean(artist).lower()
        log_prefix = f"[{artist} �C {title}]"

        logger.debug(f"{log_prefix} �9�3 Starte Genre-Erkennung")

        genre = await self.get_genre_from_musicbrainz(title, artist)
        if genre:
            logger.info(f"{log_prefix} �7�3 Genre ��ber MusicBrainz: {genre}")
            return genre

        genre = await self.get_genre_from_genius(title, artist)
        if genre:
            logger.info(f"{log_prefix} �7�3 Genre ��ber Genius: {genre}")
            return genre

        genre = await self.get_genre_from_lastfm(title, artist)
        if genre:
            logger.info(f"{log_prefix} �7�3 Genre ��ber Last.fm: {genre}")
            return genre

        genre = self.artist_genre_map.get(clean_artist)
        if genre:
            logger.info(f"{log_prefix} �6�7�1�5 Fallback-Genre ��ber Artist-Zuordnung: {genre}")
        else:
            logger.warning(f"{log_prefix} �7�4 Kein Genre erkennbar")

        return genre

    async def get_genre_from_musicbrainz(self, title: str, artist: str) -> Optional[str]:
        return None

    async def get_genre_from_genius(self, title: str, artist: str) -> Optional[str]:
        return None

    async def get_genre_from_lastfm(self, title: str, artist: str) -> Optional[str]:
        return None