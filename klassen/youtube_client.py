import asyncio
import httpx
import yt_dlp
import time
from difflib import SequenceMatcher

from logger import log_info, log_error, log_warning

class YouTubeClient:
    """
    YouTube-Client, der Song-Thumbnails durch intelligente Suche mit Caching liefert.
    """
    def __init__(self):
        self.cache = {}  # {(artist, title): bytes}
        self.ydl_base_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }

    async def fetch_thumbnail(self, title: str, artist: str) -> bytes | None:
        query_key = (artist.lower().strip(), title.lower().strip())
        if query_key in self.cache:
            log_info(f"🧠 Thumbnail aus Cache: {artist} - {title}", "YouTubeClient")
            return self.cache[query_key]

        search_queries = ["ytsearch1", "ytsearch5"]
        for search_type in search_queries:
            result = await self._fetch_thumbnail_internal(title, artist, search_type)
            if result:
                self.cache[query_key] = result
                return result

        return None

    async def _fetch_thumbnail_internal(self, title: str, artist: str, search_type: str) -> bytes | None:
        search_query = f"{artist} - {title}"
        log_info(f"🔍 YouTube-Suche ({search_type}): '{search_query}'", "YouTubeClient")
        start = time.perf_counter()

        ydl_opts = self.ydl_base_opts.copy()
        ydl_opts["default_search"] = search_type

        try:
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(
                    None,
                    lambda: ydl.extract_info(search_query, download=False)
                )

            entries = info.get("entries", [info])
            if not entries:
                log_warning(f"⚠️ Keine Ergebnisse für '{search_query}'", "YouTubeClient")
                return None

            # Wähle bestes Video
            best_entry = self._select_best_match(entries, title, artist)
            if not best_entry:
                log_warning(f"⚠️ Kein passender Treffer für '{search_query}'", "YouTubeClient")
                return None

            thumbnail_url = best_entry.get("thumbnail")
            if not thumbnail_url:
                log_warning(f"⚠️ Kein Thumbnail in Treffer '{best_entry.get('title')}'", "YouTubeClient")
                return None

            # Lade das Thumbnail
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(thumbnail_url)
                response.raise_for_status()

                duration = time.perf_counter() - start
                log_info(f"🖼️ YouTube-Thumbnail geladen ({len(response.content)} Bytes, {duration:.2f}s)", "YouTubeClient")
                return response.content

        except Exception as e:
            log_error(f"❌ Fehler bei YouTube-Abfrage ({search_type}): {e}", "YouTubeClient")
            return None

    def _select_best_match(self, entries, title, artist):
        """Wählt den besten Treffer anhand von Titel-/Künstler-Ähnlichkeit und Videolänge."""
        def score(entry):
            entry_title = entry.get("title", "").lower()
            length = entry.get("duration", 0) or 0

            title_match = self._similarity(title.lower(), entry_title)
            artist_match = self._similarity(artist.lower(), entry_title)

            # Zu kurze Clips ignorieren (z. B. Trailer oder Jingles)
            length_penalty = 1.0 if length >= 30 else 0.5

            return (title_match * 0.6 + artist_match * 0.4) * length_penalty

        best = max(entries, key=score, default=None)
        if best:
            log_info(f"🏆 Bester Treffer: '{best.get('title')}' ({best.get('duration', 0)}s)", "YouTubeClient")
        return best

    def _similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()


#client = YouTubeClient()
#thumb_bytes = await client.fetch_thumbnail("Stadtastronauten", "Bosse")

#if thumb_bytes:
#    with open("cover.jpg", "wb") as f:
#        f.write(thumb_bytes)