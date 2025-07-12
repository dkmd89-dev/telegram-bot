import requests
import logging
from typing import Optional, List
from config import Config
from helfer.genre_config import GENRE_MAP, GENRE_PRIORITY, METADATA_DEFAULTS

logger = logging.getLogger("yt_music_bot")

def fetch_lastfm_artist_tags(artist_name: str) -> Optional[List[str]]:
    """
    Holt die Tags (Genres) eines Künstlers über Last.fm.
    """
    api_key = Config.LASTFM_API_KEY
    if not api_key:
        logger.warning("⚠️ Kein Last.fm API Key in Config vorhanden.")
        return None

    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "artist.gettoptags",
        "artist": artist_name,
        "api_key": api_key,
        "format": "json"
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        if "toptags" in data and "tag" in data["toptags"]:
            tags = data["toptags"]["tag"]
            # Sortiere nach Beliebtheit (count)
            sorted_tags = sorted(tags, key=lambda x: int(x.get("count", 0)), reverse=True)
            top_tags = [t["name"] for t in sorted_tags if int(t.get("count", 0)) > 0]
            logger.debug(f"🏷️ Last.fm Artist-Tags für '{artist_name}': {top_tags}")
            return top_tags
        else:
            logger.warning(f"⚠️ Keine Tags für Artist '{artist_name}' bei Last.fm gefunden.")
            return None
    except Exception as e:
        logger.error(f"❌ Fehler beim Abrufen von Last.fm Artist-Tags: {e}")
        return None

def normalize_genre(tag: str) -> str:
    """
    Gibt das normalisierte Genre zurück, basierend auf der GENRE_MAP.
    Wenn kein Mapping existiert, wird der Titel zurückgegeben (z. B. "Jazz" aus "jazz").
    """
    tag_lc = tag.lower().strip()
    return GENRE_MAP.get(tag_lc, tag_lc.title())

def pick_best_genre(tags: list[str]) -> str:
    """
    Wählt das passendste Genre aus einer Liste von Tags.
    - Führt Mapping über GENRE_MAP durch
    - Bewertet anhand von GENRE_PRIORITY
    - Gibt das erste gültige Genre oder einen Default zurück
    """
    if not tags:
        return METADATA_DEFAULTS.get("genre", "Other")

    normalized = [normalize_genre(tag) for tag in tags]

    # Priorisiere anhand der definierten Reihenfolge
    for preferred in GENRE_PRIORITY:
        if preferred in normalized:
            return preferred

    # Fallback: erstes normalisiertes Tag
    return normalized[0] if normalized else METADATA_DEFAULTS.get("genre", "Other")

def extract_genre_from_artist_tags(artist_tags: list[str]) -> str:
    """
    Nutzt Last.fm Artist-Tags zur Genre-Erkennung.
    Führt zuerst Normalisierung durch und wählt dann das beste Genre aus.
    """
    return pick_best_genre(artist_tags)
