# genius_client.py

import asyncio
import aiohttp
from difflib import SequenceMatcher
from logger import log_error, log_debug, log_info, log_warning
from klassen.clean_artist import CleanArtist
from klassen.artist_title_handler import clean_input_artist_title  # ✅ NEU
from config import Config
import async_timeout
import os
import json
from bs4 import BeautifulSoup

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

class GeniusClient:
    def __init__(self, artist_cleaner: CleanArtist):
        self.artist_cleaner = artist_cleaner
        self.genius_api = Config.genius
        self.cache_dir = "lyrics_cache"
        os.makedirs(self.cache_dir, exist_ok=True)

    def _is_valid_lyrics(self, lyrics: str) -> bool:
        return bool(lyrics and lyrics.strip() and lyrics.lower().strip() != "lyrics not available")

    async def _scrape_genius_lyrics_html(self, url: str) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        log_warning(f"⚠️ Genius HTML-Request fehlgeschlagen ({response.status}) für {url}")
                        return ""
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    containers = soup.select('div[data-lyrics-container]')
                    if not containers:
                        log_warning("⚠️ Kein Lyrics-Container im HTML gefunden.")
                        return ""
                    return "\n\n".join([div.get_text(separator="\n").strip() for div in containers])
        except Exception as e:
            log_error(f"⚠️ Fehler beim HTML-Scrape von Genius: {str(e)}")
            return ""

    async def fetch_metadata(self, raw_title: str, raw_artist: str) -> dict:
        try:
            async with async_timeout.timeout(Config.GENIUS_TIMEOUT):
                # ✅ NEU: Funktion nutzen statt Klasse
                clean_artist, clean_title = clean_input_artist_title(f"{raw_artist} - {raw_title}")
                clean_artist_str = self.artist_cleaner.clean(clean_artist)
                search_query = f"{clean_title} {clean_artist_str}"
                log_debug(f"Starte Genius-Suche mit Query: '{search_query}'")

                search_results = await asyncio.to_thread(
                    self.genius_api.search_songs,
                    search_query,
                    per_page=Config.GENIUS_CONFIG["max_results"],
                )

                if not search_results or "hits" not in search_results or not search_results["hits"]:
                    log_info(f"ℹ️ Keine Genius-Ergebnisse für '{search_query}' gefunden.")
                    return {}

                best_match = None
                best_score = 0

                for hit in search_results["hits"]:
                    result = hit.get("result", {})
                    hit_title = result.get("title", "")
                    hit_artist_name = result.get("primary_artist", {}).get("name", "")

                    title_sim = similarity(clean_title, hit_title)
                    artist_sim = similarity(clean_artist_str, hit_artist_name)

                    if artist_sim >= 0.9:
                        similarity_score = (title_sim * 0.5) + (artist_sim * 0.5)
                        threshold = 0.5
                    else:
                        similarity_score = (title_sim * 0.65) + (artist_sim * 0.35)
                        threshold = Config.GENIUS_CONFIG["auto_match_threshold"]

                    log_debug(
                        f"  Kandidat: '{hit_artist_name}' - '{hit_title}' | Score: {similarity_score:.2f} "
                        f"(Titel: {title_sim:.2f}, Künstler: {artist_sim:.2f}), Threshold: {threshold:.2f}"
                    )

                    if similarity_score > best_score and similarity_score >= threshold:
                        best_score = similarity_score
                        best_match = result

                if not best_match:
                    log_info(f"ℹ️ Kein ausreichend gutes Genius-Match gefunden (Bester Score: {best_score:.2f}).")
                    return {}

                log_info(f"✅ Bestes Genius-Match gefunden: '{best_match.get('full_title')}' mit Score {best_score:.2f}")

                song_id = best_match["id"]
                cache_file_path = os.path.join(self.cache_dir, f"{song_id}.json")

                if os.path.exists(cache_file_path):
                    log_info(f"💾 Cache-Treffer für Song-ID: {song_id}. Lade aus Datei.")
                    with open(cache_file_path, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                        if self._is_valid_lyrics(cached_data.get("lyrics")):
                            return cached_data
                        else:
                            log_warning(f"❌ Lyrics im Cache leer für Song-ID: {song_id}. Erzwinge erneuten Abruf.")

                song_details = await asyncio.to_thread(self.genius_api.song, song_id)
                song_data = song_details.get("song", {})

                genius_url = song_data.get("url")
                if genius_url:
                    log_info(f"Genius-URL: {genius_url}")

                lyrics_text = song_data.get("lyrics", {}).get("plain")

                if not self._is_valid_lyrics(lyrics_text):
                    log_warning(f"❌ Lyrics leer via API, versuche HTML-Fallback: {genius_url}")
                    lyrics_text = await self._scrape_genius_lyrics_html(genius_url)
                    if lyrics_text:
                        log_info(f"✅ Lyrics erfolgreich per HTML geladen (Länge: {len(lyrics_text)})")
                    else:
                        log_warning(f"❌ Auch HTML-Fallback fehlgeschlagen für {genius_url}")

                release_date_str = song_data.get("release_date")
                year = release_date_str[:4] if release_date_str and len(release_date_str) >= 4 else None
                primary_tag_name = song_data.get("primary_tag", {}).get("name") if song_data.get("primary_tag") else None

                metadata_to_return = {
                    "title": song_data.get("title"),
                    "artist": song_data.get("primary_artist", {}).get("name"),
                    "lyrics": lyrics_text,
                    "cover_url": song_data.get("song_art_image_url"),
                    "album": song_data.get("album", {}).get("name") if song_data.get("album") else None,
                    "year": year,
                    "genre": primary_tag_name,
                    "tags": [primary_tag_name] if primary_tag_name else [],
                    "genius_url": genius_url
                }

                with open(cache_file_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata_to_return, f, ensure_ascii=False, indent=4)
                log_info(f"💾 Metadaten für Song-ID {song_id} im Cache gespeichert.")

                return metadata_to_return

        except (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError) as e:
            log_error(f"Genius Netzwerkfehler: {str(e)}", {"title": raw_title, "artist": raw_artist})
            return {}
        except asyncio.TimeoutError:
            log_warning("⏱️ Genius-Anfrage überschritten", {"title": raw_title, "artist": raw_artist})
            return {}
        except Exception as e:
            log_error(f"Genius Error: {str(e)}", {"title": raw_title, "artist": raw_artist})
            return {}