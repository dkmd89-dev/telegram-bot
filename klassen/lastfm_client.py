# klassen/lastfm_client.py

import asyncio
import pylast
from typing import Optional, Dict, List, Any, Tuple
from logger import log_error, log_debug, log_info, log_warning
from config import Config
import async_timeout

def safe_get(value):
    """Hilfsfunktion zum Absichern leerer Feldwerte."""
    return str(value).strip() if value else None

class LastFMClient:
    """
    Eine Klasse zur Abfrage von Metadaten von Last.fm.
    """
    def __init__(self):
        self.lastfm_network = pylast.LastFMNetwork(
            api_key=Config.LASTFM_API_KEY,
            api_secret=Config.LASTFM_API_SECRET,
        )

    def _get_lastfm_data(self, title: str, artist: str) -> Tuple[Optional[Dict], List]:
        """Hilfsfunktion, um Track-Infos und Top-Tags von Last.fm zu holen."""
        try:
            log_debug(f"Fetching Last.fm data for track: '{artist}' - '{title}'")
            track = self.lastfm_network.get_track(artist, title)
            if not track:
                return None, []

            album_title = track.get_album().get_title() if track.get_album() else None
            wiki_summary = track.get_wiki_summary() if track.get_wiki_content() else None
            tags = track.get_top_tags(limit=5) or []

            info = {
                "title": safe_get(track.get_title()),
                "artist": safe_get(track.get_artist().get_name()),
                "album": album_title,
                "listeners": track.get_listener_count(),
                "playcount": track.get_playcount(),
                "wiki": wiki_summary
            }
            return info, tags

        except pylast.WSError as e:
            log_warning(f"❌ Last.fm API-Fehler: {str(e)}", {"artist": artist, "title": title})
            return None, []
        except Exception as e:
            log_error(f"❌ Unerwarteter Fehler bei Last.fm: {str(e)}", {"artist": artist, "title": title})
            return None, []

    async def fetch_metadata(self, title: str, artist: str) -> Dict[str, Any]:
        """Holt Metadaten von der Last.fm API."""
        try:
            async with async_timeout.timeout(Config.LASTFM_TIMEOUT):
                log_debug(f"🎵 Last.fm Anfrage: {artist} – {title}")
                track_info, tags = await asyncio.to_thread(self._get_lastfm_data, title, artist)

                if not track_info:
                    log_info(f"ℹ️ Keine Last.fm-Daten für {artist} - {title}")
                    return {}

                tag_names = [tag.item.get_name() for tag in tags if hasattr(tag.item, "get_name")]

                return {
                    "tags": tag_names,
                    "listeners": track_info.get("listeners"),
                    "playcount": track_info.get("playcount"),
                    "album": track_info.get("album"),
                    "wiki": track_info.get("wiki"),
                    "genre": None
                }
        except asyncio.TimeoutError:
            log_warning("⏱️ Last.fm-Anfrage überschritten", {"artist": artist, "title": title})
            return {}
        except Exception as e:
            log_error(f"❌ Last.fm Fehler: {str(e)}", {"artist": artist, "title": title})
            return {}