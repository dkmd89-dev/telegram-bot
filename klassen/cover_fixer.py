import asyncio
import aiohttp
import io
from typing import Optional
from cachetools import TTLCache
from PIL import Image
from logger import log_error, log_info, log_debug, log_warning
from config import Config
from mutagen.mp4 import MP4Cover


class CoverFixer:
    """Handles retrieval, validation, and caching of cover art for music files."""

    _cover_cache = TTLCache(maxsize=200, ttl=3600)  # 1 Stunde Cache

    def __init__(self, musicbrainz_client, genius_client, lastfm_client, debug: bool = False):
        self.musicbrainz_client = musicbrainz_client
        self.genius_client = genius_client
        self.lastfm_client = lastfm_client
        self.debug = debug

        self.supported_formats = ['image/jpeg', 'image/png']
        self.max_size = Config.MAX_COVER_SIZE
        self.min_resolution = (300, 300)
        self.max_resolution = (1000, 1000)

    async def fetch_cover(self, title: str, artist: str, album: str = None) -> Optional[bytes]:
        """
        Sucht nach einem Cover, validiert es, speichert es im Cache und gibt die Bilddaten zurück.
        """
        cache_key = f"{artist.lower()}:{title.lower()}:{album or ''}"
        if cache_key in self._cover_cache:
            if self.debug:
                log_debug(f"✅ Cache Hit für '{cache_key}'", "CoverFixer")
            return self._cover_cache[cache_key]

        log_info(f"🔍 Suche Cover für: {artist} - {title}", "CoverFixer")

        sources = [
            (self.genius_client, self._fetch_genius_cover),
            (self.musicbrainz_client, self._fetch_musicbrainz_cover),
            (self.lastfm_client, self._fetch_lastfm_cover),
        ]

        for client, fetch_method in sources:
            try:
                downloaded_data = await fetch_method(title, artist, album)
                if self.debug:
                    log_debug(f"📦 Antwort von {client.__class__.__name__}: {bool(downloaded_data)}", "CoverFixer")

                if downloaded_data:
                    processed_data = await self._validate_and_resize_cover(downloaded_data)
                    
                    if processed_data:
                        self._cover_cache[cache_key] = processed_data
                        log_info(f"✅ Cover erfolgreich geladen und verarbeitet von {client.__class__.__name__}", "CoverFixer")
                        return processed_data
                        
            except Exception as e:
                log_warning(f"⚠️ Fehler bei der Verarbeitung von {client.__class__.__name__}: {e}", "CoverFixer")

        log_error(f"❌ Kein gültiges Cover für '{artist} - {title}' gefunden", "CoverFixer")
        return None

    async def _fetch_genius_cover(self, title: str, artist: str, album: str = None) -> Optional[bytes]:
        metadata = await self.genius_client.fetch_metadata(title, artist)
        cover_url = metadata.get("cover_url")
        if self.debug:
            log_debug(f"Genius Cover-URL: {cover_url}", "CoverFixer")
        if cover_url:
            return await self._download_cover(cover_url)
        return None

    async def _fetch_musicbrainz_cover(self, title: str, artist: str, album: str = None) -> Optional[bytes]:
        metadata = await self.musicbrainz_client.fetch_metadata(title, artist)
        release_id = metadata.get("release_id")
        if self.debug:
            log_debug(f"MusicBrainz Release ID: {release_id}", "CoverFixer")

        if release_id:
            try:
                import musicbrainzngs
                cover_data = await asyncio.to_thread(
                    musicbrainzngs.get_image_list, release_id
                )
                images = cover_data.get("images", [])
                for image in images:
                    if image.get("approved") and image.get("image"):
                        return await self._download_cover(image["image"])
            except Exception as e:
                log_warning(f"MusicBrainz Cover-Fehler: {e}", "CoverFixer")
        return None

    async def _fetch_lastfm_cover(self, title: str, artist: str, album: str = None) -> Optional[bytes]:
        metadata = await self.lastfm_client.fetch_metadata(title, artist)
        cover_url = metadata.get("image")
        if self.debug:
            log_debug(f"Last.fm Cover-URL: {cover_url}", "CoverFixer")
        if cover_url:
            return await self._download_cover(cover_url)
        return None

    async def _download_cover(self, url: str) -> Optional[bytes]:
        if self.debug:
            log_debug(f"📥 Lade Cover von: {url}", "CoverFixer")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=Config.COVER_DOWNLOAD_TIMEOUT) as response:
                    response.raise_for_status()
                    content = await response.read()

                    if self.debug:
                        log_debug(f"⬇️ Geladene Größe: {len(content)} Bytes", "CoverFixer")

                    if len(content) <= self.max_size:
                        return content
                    log_warning(f"⚠️ Cover zu groß: {len(content)} Bytes. Wird zur Validierung weitergeleitet.", "CoverFixer")
                    # Wir erlauben hier größere Dateien, da die Validierung sie skaliert
                    return content
        except Exception as e:
            log_error(f"❌ Fehler beim Download von {url}: {e}", "CoverFixer")
        return None

    async def _validate_and_resize_cover(self, cover_data: bytes) -> Optional[bytes]:
        """
        Validiert das Cover, skaliert es bei Bedarf und konvertiert es zu JPEG.
        Gibt die validierten und verarbeiteten Bilddaten zurück oder None bei Fehlern.
        """
        try:
            img = Image.open(io.BytesIO(cover_data))
            if self.debug:
                log_debug(f"🖼️ Bildformat: {img.format}, Auflösung: {img.size}", "CoverFixer")

            if img.format.lower() not in ['jpeg', 'png']:
                log_warning(f"❌ Nicht unterstütztes Format: {img.format}", "CoverFixer")
                return None

            if img.size[0] < self.min_resolution[0] or img.size[1] < self.min_resolution[1]:
                log_warning(f"⚠️ Auflösung zu niedrig: {img.size}", "CoverFixer")
                return None
            
            resized = False
            if img.size[0] > self.max_resolution[0] or img.size[1] > self.max_resolution[1]:
                log_info(f"🔧 Skaliere Cover von {img.size} auf {self.max_resolution}", "CoverFixer")
                img = img.resize(self.max_resolution, Image.Resampling.LANCZOS)
                resized = True
            
            if resized or img.format.lower() == 'png':
                output = io.BytesIO()
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(output, format='JPEG', quality=90)
                new_data = output.getvalue()
                log_debug(f"💾 Bild konvertiert/skaliert. Alte Größe: {len(cover_data)} -> Neue Größe: {len(new_data)}", "CoverFixer")
                return new_data

            return cover_data

        except Exception as e:
            log_error(f"❌ Fehler bei Cover-Validierung: {e}", "CoverFixer")
            return None

    def embed_cover(self, audio, cover_data: Optional[bytes]) -> bool:
        """Bettet das Cover in eine Audiodatei ein."""
        if not cover_data:
            log_warning("Kein Cover zum Einbetten vorhanden", "CoverFixer")
            return False
        try:
            # Da wir zu JPEG standardisieren, können wir das Format hier festlegen.
            audio["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
            return True
        except Exception as e:
            log_error(f"❌ Fehler beim Einbetten des Covers: {str(e)}", "CoverFixer")
            return False