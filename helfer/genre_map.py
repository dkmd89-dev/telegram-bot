import logging
from pathlib import Path
from collections import Counter
from typing import Optional, List, Dict  

# Logging einrichten
def setup_genre_logger():
    logger = logging.getLogger("genre_map")
    logger.setLevel(logging.DEBUG)

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    log_path = Path("/mnt/media/musiccenter/logs/genre.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    logger.addHandler(file_handler)
    return logger

logger = setup_genre_logger()

# Globale Zähler für Statistik
genre_stats = Counter()

BAD_GENRES = {
    "", "none", "unbekannt", "unknown", "test", "testgenre", "default",
    "musik", "music", "germany", "female", "cover",
    "s artist", "feat", "featuring", "intro", "favorites", "awesome",
    "pop/rock", "various", "random", "no genre", "soundtrack",
    "soundtracks", "songs", "mix", "remix", "live", "single", "audio",
    # NEUE ERGÄNZUNGEN ZU BAD_GENRES (basierend auf der bereitgestellten Liste)
    "love at first listen",
    "fm4",
    "warm inside",
    "myspotigrambot",
    "4 stars",
    "australian number one",
    "black",
    "finessin",
    "fuck feat tags",
    "osc 43 - timmins",
    "outernatia song contest 99",
    "best 2018 singles",
    "great quality stuff",
    "party",
    "modern german female pop",
    "colors",
    "favorite",
    "nocne wyciszenie",
    "wake-up song",
    # Weitere Genres aus deiner Liste, die in BAD_GENRES aufgenommen werden sollten
    "2020s", # Basierend auf deiner Liste "Top 16 Genres"
    "2024",  # Basierend auf deiner Liste "Top 16 Genres"
    "the color black", # Basierend auf deiner Liste "Top 16 Genres" (hier klein geschrieben für Konsistenz)
    "2023",  # Basierend auf deiner Liste "Top 16 Genres"
    "bbc radio1 playlist 2016", # Basierend auf deiner Liste "Top 16 Genres" (hier klein geschrieben)
}

GENRE_MAP = {
    # Hip-Hop / Rap
    "hip hop": "Hip-Hop",
    "hip-hop": "Hip-Hop",
    "hiphop": "Hip-Hop",
    "german hip hop": "Hip-Hop",
    "cloud rap": "Hip-Hop",
    "trap": "Hip-Hop",
    "southern hip hop": "Hip-Hop",
    "rap": "Hip-Hop",
    "deutschrap": "Hip-Hop",
    "conscious hip hop": "Hip-Hop",
    "experimental hip hop": "Hip-Hop",

    # Rock
    "rock": "Rock",
    "hard rock": "Rock",
    "punk rock": "Rock",
    "pop rock": "Rock",
    "alternative rock": "Rock",
    "classic rock": "Rock",
    "garage rock": "Rock",
    "indie rock": "Rock",
    "deutschrock": "Rock",
    "pop punk": "Rock",

    # Pop
    "pop": "Pop",
    "electropop": "Pop",
    "dance pop": "Pop",
    "german": "Pop",
    "deutsch": "Pop",
    "schlager": "Pop",
    "mainstream": "Pop",
    "synthpop": "Pop",

    # Electronic
    "edm": "Electronic",
    "electronic": "Electronic",
    "electro house": "Electronic",
    "house": "Electronic",
    "deep house": "Electronic",
    "tropical house": "Electronic",
    "techno": "Electronic",
    "progressive house": "Electronic",
    "electronica": "Electronic",
    "chillout": "Electronic",
    "chill": "Electronic",
    "ambient": "Electronic",
    "minimal": "Electronic",
    "trance": "Electronic",
    "dubstep": "Electronic",
    "dance": "Electronic",

    # R&B / Soul
    "rnb": "R&B",
    "r&b": "R&B",
    "soul": "R&B",
    "neo soul": "R&B",
    "funk": "R&B",

    # Reggae
    "reggae": "Reggae",
    "dancehall": "Reggae",
    "roots reggae": "Reggae",

    # Folk / Acoustic
    "folk": "Folk",
    "singer-songwriter": "Folk",
    "acoustic": "Folk",

    # Jazz, Blues, Classical
    "classical": "Classical",
    "jazz": "Jazz",
    "blues": "Blues",

    # Feiertagsmusik
    "christmas": "Holiday",
    "christmas songs": "Holiday",
    "xmas": "Holiday",

    # Entfernte Werte (Personen, irrelevantes, Jahreszahlen etc.)
    "drake": None,
    "kygo": None,
    "sido": None,
    "travis scott": None,
    "young thug": None,
    "2pac": None,
    "boehse onkelz": None,
    "seeed": None,
    "migos": None,
    "vincent": None,
    "cro": None,
    "capital bra": None,
    "bushido": None,
    "shindy": None,
    "apache 207": None,
    "katja krasavice": None,
    "jamule": None,
    "ava max": None,
    "bonnie mckee": None,
    "one republic": None,
    "peewee longway": None,
    "big sean": None,
    "billy raffoul": None,
    "jhart": None,
    "rich homie quan": None,
    "wrabel": None,

    "2010": None,
    "2011": None,
    "2012": None,
    "2013": None,
    "2014": None,
    "2015": None,
    "2016": None,
    "2017": None,
    "2018": None,
    "2019": None,
    "2020": None,
    "2021": None,
    "2022": None,
    "2023": None,
    "2024": None,
    "2025": None,

    "2015 single": None,
    "2020s": None,
    "the 1975": None,
}

def normalize_genre(raw_genre: str, artist_genre: Optional[str] = None) -> str:
    """Bereinigt, normalisiert und mapped ein Genre.
    Verwendet optional ein Künstler-Genre als Fallback, falls das Roh-Genre unbrauchbar ist.
    """
    normalized_song_genre = ""
    if raw_genre:
        genre = raw_genre.strip().lower()
        if genre in BAD_GENRES:
            logger.info(f"❌ Ignoriertes Song-Genre: '{raw_genre}' (unbrauchbar)")
            genre_stats["entfernt_song"] += 1
            normalized_song_genre = ""
        elif genre in GENRE_MAP:
            mapped = GENRE_MAP[genre]
            if mapped is None:
                logger.info(f"⛔ Entferntes Song-Genre: '{raw_genre}' (irrelevant)")
                genre_stats["entfernt_song"] += 1
                normalized_song_genre = ""
            else:
                logger.debug(f"🔁 Mapping Song-Genre: '{raw_genre}' → '{mapped}'")
                genre_stats["gemappt_song"] += 1
                normalized_song_genre = mapped
        else:
            normalized_song_genre = genre.title()
            logger.debug(f"✅ Unverändertes Song-Genre: '{raw_genre}' → '{normalized_song_genre}'")
            genre_stats["unverändert_song"] += 1

    # Wenn das Song-Genre unbrauchbar ist, versuche das Künstler-Genre
    if not normalized_song_genre and artist_genre:
        cleaned_artist_genre = artist_genre.strip().lower()
        if cleaned_artist_genre in BAD_GENRES:
            logger.info(f"❌ Ignoriertes Künstler-Genre: '{artist_genre}' (unbrauchbar)")
            genre_stats["entfernt_artist"] += 1
            return ""
        elif cleaned_artist_genre in GENRE_MAP:
            mapped = GENRE_MAP[cleaned_artist_genre]
            if mapped is None:
                logger.info(f"⛔ Entferntes Künstler-Genre: '{artist_genre}' (irrelevant)")
                genre_stats["entfernt_artist"] += 1
                return ""
            logger.debug(f"🔁 Mapping Künstler-Genre: '{artist_genre}' → '{mapped}' (Fallback)")
            genre_stats["gemappt_artist_fallback"] += 1
            return mapped
        else:
            logger.debug(f"✅ Unverändertes Künstler-Genre: '{artist_genre}' → '{cleaned_artist_genre.title()}' (Fallback)")
            genre_stats["unverändert_artist_fallback"] += 1
            return cleaned_artist_genre.title()

    # Gib das normalisierte Song-Genre zurück, oder leer, wenn beides nicht zutrifft
    return normalized_song_genre


def get_genre_stats(as_text: bool = True) -> str | dict:
    """Gibt Genre-Statistiken zurück"""
    total = sum(genre_stats.values())
    stats = {
        "verarbeitet": total,
        **genre_stats
    }

    if as_text:
        # Hier habe ich die Statistik-Ausgabe angepasst, um die neuen detaillierteren Zähler zu nutzen
        return (
            f"🎧 Genre-Statistik:\n"
            f"• Gesamt verarbeitet: {total}\n"
            f"• Song-Genres gemappt: {genre_stats['gemappt_song']}\n"
            f"• Song-Genres unverändert: {genre_stats['unverändert_song']}\n"
            f"• Song-Genres entfernt: {genre_stats['entfernt_song']}\n"
            f"• Künstler-Genres als Fallback gemappt: {genre_stats['gemappt_artist_fallback']}\n"
            f"• Künstler-Genres als Fallback unverändert: {genre_stats['unverändert_artist_fallback']}\n"
            f"• Künstler-Genres als Fallback entfernt: {genre_stats['entfernt_artist']}\n"
            f"• Songs ohne gültiges Genre (nach allen Prüfungen): {genre_stats['leer']}" # Du müsstest 'leer' in normalize_genre inkrementieren, falls am Ende nichts gefunden wird
        )
    return stats