# musicbrainz_client.py
import asyncio
import musicbrainzngs
from cachetools import TTLCache
from difflib import SequenceMatcher
from logger import log_error, log_debug, log_info, log_warning
from klassen.title_cleaner import TitleCleaner
from klassen.clean_artist import CleanArtist
from config import Config
import async_timeout

# Async-kompatibler TTL-Cache
_musicbrainz_result_cache = TTLCache(maxsize=200, ttl=3600)

def similarity(a: str, b: str) -> float:
    """Berechnet Ähnlichkeit zweier Strings (0.0–1.0)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

async def cached_musicbrainz_search(query: str) -> dict:
    """Cached async-kompatible MusicBrainz-Suche."""
    if query in _musicbrainz_result_cache:
        log_debug(f"🎯 [Cache Hit] MusicBrainz: '{query}'")
        return _musicbrainz_result_cache[query]

    try:
        log_debug(f"🌐 [API Request] MusicBrainz: '{query}'")
        # Suche nach Aufnahmen (recordings) mit erweiterten Informationen
        result = await asyncio.to_thread(
            musicbrainzngs.search_recordings, query=query, limit=10, includes=["artist-credits", "releases"]
        )
        _musicbrainz_result_cache[query] = result
        return result
    except musicbrainzngs.NetworkError as e:
        log_error(f"📡 MusicBrainz network error: {str(e)}", {"query": query})
        return {}
    except Exception as e:
        log_error(f"❌ MusicBrainz cache error: {str(e)}", {"query": query})
        return {}

class MusicBrainzClient:
    def __init__(self, artist_cleaner: CleanArtist, log_level: str = "debug"):
        self.artist_cleaner = artist_cleaner
        self.log_level = log_level.lower()
        musicbrainzngs.set_useragent("yt_music_bot", "1.0", "support@example.com")

    def _log(self, level: str, msg: str, context: dict = None):
        """Interner Logger basierend auf gesetztem Log-Level."""
        levels = ["debug", "info", "warning", "error"]
        if levels.index(level) >= levels.index(self.log_level):
            if level == "debug":
                log_debug(msg, context)
            elif level == "info":
                log_info(msg, context)
            elif level == "warning":
                log_warning(msg, context)
            elif level == "error":
                log_error(msg, context)

    async def fetch_metadata(self, title: str, artist: str) -> dict:
        """Holt Metadaten von MusicBrainz mit Fallback-Strategie."""
        try:
            async with async_timeout.timeout(Config.MUSICBRAINZ_TIMEOUT):
                clean_title = TitleCleaner.clean_title(title)
                clean_artist = self.artist_cleaner.clean(artist)

                self._log("info", f"🎵 MusicBrainz Suche: '{clean_artist}' – '{clean_title}'")
                
                # Optimierte Query: Sucht nach dem Titel und nutzt den Künstlernamen als Filterkriterium
                query = f'recording:"{clean_title}" AND artist:"{clean_artist}"'
                
                result = await cached_musicbrainz_search(query)
                recordings = result.get("recording-list", [])

                if not recordings:
                    # Fallback: Suche nur nach dem Titel, falls die erste Suche scheitert
                    self._log("info", f"❓ Keine Ergebnisse für die kombinierte Query. Fallback auf Titelsuche.")
                    query = f'"{clean_title}"'
                    result = await cached_musicbrainz_search(query)
                    recordings = result.get("recording-list", [])

                if recordings:
                    self._log("debug", f"🔁 {len(recordings)} Aufnahmen gefunden.")
                    best = self._get_best_match(recordings, clean_title, clean_artist)
                    if best:
                        return await self._build_metadata(best)

                self._log("warning", f"⚠️ Kein brauchbares Ergebnis für '{artist}' – '{title}'")
                return {}

        except musicbrainzngs.ResponseError as e:
            self._log("error", f"❌ MusicBrainz API Error: {str(e)}", {"title": title, "artist": artist})
        except asyncio.TimeoutError:
            self._log("warning", "⏱️ MusicBrainz Anfrage abgelaufen", {"title": title, "artist": artist})
        except Exception as e:
            self._log("error", f"💥 Unerwarteter MusicBrainz Fehler: {str(e)}", {"title": title, "artist": artist})
        return {}

    def _get_best_match(self, recordings, clean_title: str, clean_artist: str):
        """Findet das beste Ergebnis basierend auf einem gewichteten Score."""
        best_score = 0
        best_match = None

        for r in recordings:
            rec_title = r.get("title", "")
            # artist-credit-phrase ist eine bereits formatierte Zeichenkette der Künstler
            rec_artist_phrase = r.get("artist-credit-phrase", "")

            title_sim = similarity(clean_title, rec_title)
            artist_sim = similarity(clean_artist, rec_artist_phrase)
            
            # Gewichteter Score: Der Titel ist oft wichtiger als der Künstler
            score = (title_sim * 0.7) + (artist_sim * 0.3)
            
            # Bonus, wenn der Künstler exakt übereinstimmt
            if clean_artist.lower() == rec_artist_phrase.lower():
                score += 0.1
            
            self._log("debug", f"   Kandidat: '{rec_artist_phrase}' - '{rec_title}' | Score: {score:.2f} (Titel: {title_sim:.2f}, Künstler: {artist_sim:.2f})")

            if score > best_score:
                best_score = score
                best_match = r
        
        # Nur einen Treffer zurückgeben, der eine Mindestähnlichkeit aufweist
        if best_score >= Config.MUSICBRAINZ_MIN_SIMILARITY:
            self._log("info", f"✅ Bestes Match: '{best_match.get('artist-credit-phrase')}' - '{best_match.get('title')}' mit Score {best_score:.2f}")
            return best_match
        
        return None


    async def _build_metadata(self, match: dict) -> dict:
        """Extrahiert und ergänzt Metadaten effizient."""
        # Priorisiere Daten aus dem 'match'-Objekt, um API-Aufrufe zu sparen
        release_list = match.get("release-list", [])
        first_release = release_list[0] if release_list else {}
        
        release_id = first_release.get("id")
        release_group = first_release.get("release-group", {})

        # Hole Release-Jahr aus dem frühesten verfügbaren Datum
        release_date = match.get("first-release-date") or release_group.get("first-release-date")
        release_year = release_date[:4] if release_date and len(release_date) >= 4 else None

        # Tags sind oft nur im vollständigen Release-Group-Objekt enthalten
        tags = [t["name"] for t in release_group.get("tags", [])]
        
        # Wenn wir mehr Details (wie Album-Artist) benötigen, machen wir den gezielten API-Aufruf
        album_artist = first_release.get("artist-credit-phrase")
        if not album_artist and release_id:
            try:
                release_data = await asyncio.to_thread(
                    musicbrainzngs.get_release_by_id, release_id, includes=["artist-credits"]
                )
                album_artist = release_data.get("release", {}).get("artist-credit-phrase")
            except Exception:
                self._log("warning", f"Konnte Album-Künstler für Release ID {release_id} nicht abrufen.")


        return {
            "title": match.get("title"),
            "artist": match.get("artist-credit-phrase"),
            "album": release_group.get("title"),
            "track_number": int(first_release.get("medium-track-count", 0)) if first_release.get("medium-track-count") else None,
            "release_date": release_date,
            "year": release_year,
            "album_artist": album_artist,
            "tags": tags,
            "genre": None # Genre wird von Genius geholt
        }