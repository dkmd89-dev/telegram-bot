# helfer/genre_fixer.py

import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, List
from klassen.genius_client import GeniusClient
from klassen.musicbrainz_client import MusicBrainzClient
from klassen.lastfm_client import LastFMClient
from klassen.clean_artist import CleanArtist
from helfer.artist_map import ARTIST_GENRE_MAP

class GenreFetcher:
    """Bestimmt das Genre basierend auf Titel und KÃ¼nstler mit Caching, Logging und Fallback."""

    def __init__(self):
        self.cleaner = CleanArtist()
        self.genius = GeniusClient(self.cleaner)
        self.musicbrainz = MusicBrainzClient()
        self.lastfm = LastFMClient()
        self.cache = {}

        self.artist_genre_map = ARTIST_GENRE_MAP

        self.logger = logging.getLogger("GenreFetcher")
        self.logger.setLevel(logging.DEBUG)

        # Dateibasiertes Logging mit Rotation
        handler = RotatingFileHandler("logs/genre_fixer.log", maxBytes=2_000_000, backupCount=3)
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    async def get_genre(self, title: str, artist: str) -> Optional[str]:
        clean_artist = artist.strip().lower()
        cache_key = f"{clean_artist}|{title.strip().lower()}"
        log_prefix = f"[{artist} â1¤7 {title}]"

        # Caching
        if cache_key in self.cache:
            self.logger.debug(f"{log_prefix} â1¤7 Genre aus Cache: {self.cache[cache_key]}")
            return self.cache[cache_key]

        self.logger.debug(f"{log_prefix} ð Starte Genre-Erkennung")

        genre = await self.get_genre_from_musicbrainz(title, artist)
        if genre:
            genre = self._normalize_genre(genre)
            self.logger.info(f"{log_prefix} â1¤7 Genre Ã¼ber MusicBrainz: {genre}")
            self.cache[cache_key] = genre
            return genre

        genre = await self.get_genre_from_genius(title, artist)
        if genre:
            genre = self._normalize_genre(genre)
            self.logger.info(f"{log_prefix} â1¤7 Genre Ã¼ber Genius: {genre}")
            self.cache[cache_key] = genre
            return genre

        genre = await self.get_genre_from_lastfm(title, artist)
        if genre:
            genre = self._normalize_genre(genre)
            self.logger.info(f"{log_prefix} â1¤7 Genre Ã¼ber Last.fm: {genre}")
            self.cache[cache_key] = genre
            return genre

        genre = self.artist_genre_map.get(clean_artist)
        if genre:
            self.logger.info(f"{log_prefix} â¹ï¸ Fallback-Genre Ã¼ber Artist-Zuordnung: {genre}")
        else:
            self.logger.warning(f"{log_prefix} â1¤7 Kein Genre erkennbar")

        self.cache[cache_key] = genre
        return genre

    async def get_genre_from_musicbrainz(self, title: str, artist: str) -> Optional[str]:
        try:
            result = await self.musicbrainz.fetch_metadata(title, artist)
            genres = result.get("genres", [])
            return self._get_first_valid_genre(genres)
        except Exception as e:
            self.logger.warning(f"[{artist} â1¤7 {title}] â ï¸ MusicBrainz-Fehler: {e}")
            return None

    async def get_genre_from_genius(self, title: str, artist: str) -> Optional[str]:
        try:
            result = await self.genius.fetch_metadata(title, artist)
            return result.get("genre")
        except Exception as e:
            self.logger.warning(f"[{artist} â1¤7 {title}] â ï¸ Genius-Fehler: {e}")
            return None

    async def get_genre_from_lastfm(self, title: str, artist: str) -> Optional[str]:
        try:
            result = await self.lastfm.fetch_metadata(title, artist)
            genres = result.get("genres", [])
            return self._get_first_valid_genre(genres)
        except Exception as e:
            self.logger.warning(f"[{artist} â1¤7 {title}] â ï¸ Last.fm-Fehler: {e}")
            return None

    def _get_first_valid_genre(self, genres: List[str]) -> Optional[str]:
        for genre in genres:
            norm = self._normalize_genre(genre)
            if norm:
                return norm
        return None

    def _normalize_genre(self, genre: Optional[str]) -> Optional[str]:
        if not genre:
            return None
        genre = genre.strip().lower()

        # Optional: Gruppieren mehrerer Ã¤hnlicher Begriffe
        mapping = {
            "hip hop": "Hip-Hop",
            "hip-hop": "Hip-Hop",
            "rap": "Hip-Hop",
            "trap": "Trap",
            "pop": "Pop",
            "rock": "Rock",
            "r&b": "R&B",
            "tropical house": "Tropical House",
            "dance": "Dance",
            "deep house": "Deep House",
        }

        return mapping.get(genre, genre.title())