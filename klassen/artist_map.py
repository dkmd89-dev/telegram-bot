# -*- coding: utf-8 -*-
import re
from collections import defaultdict

# ---------- 1. EXPLIZITE OVERRIDES ----------

RAW_OVERRIDES = {
    "Makko": "makko",
    "MaKKo": "makko",
    "MAKKO": "makko",
    "bosse": "Bosse",
    "bosseaxel": "Bosse",
    "BosseA": "Bosse",
    "zartmann": "Zartmann",
    "dante": "Dante YN",
    "dante yn": "Dante YN",
    "kygo": "Kygo",
    "KygoMusic": "Kygo",
    "möwe": "MÖWE",
    "MÖWE": "MÖWE",
    "Mowe": "MÖWE",
    "robin schulz": "Robin Schulz",
    "RobinSchulz": "Robin Schulz",
    "lea": "LEA",
    "LeA": "LEA",
    "Lea": "LEA",
    "badchieff": "Badchieff",
    "aggu31": "Ski Aggu",
    "bausa": "BAUSA",
    "bausashaus": "BAUSA",
    "sido": "Sido",
    "SIDO": "Sido",
    "01099": "01099",
}

ARTIST_OVERRIDES = {k.lower(): v for k, v in RAW_OVERRIDES.items()}

# ---------- 2. REGEX-REGELN (ARTIST_RULES) ----------

ARTIST_RULES = [
    (r"\s*\(feat\..+?\)", ""),
    (r"\s*&\s*", ", "),
    (r"\s*vs\.?\s*", ", "),
    (r"\s*x\.?\s*", ", "),
    (r"\s*X\.?\s*", ", "),
    (r"^makko.*", "makko"),
    (r"^Bosse.*", "Bosse"),
    (r".*Ski Aggu.*", "Ski Aggu"),
    (r"^lea.*", "LEA"),
    (r"^sido.*", "Sido"),
    (r"^bausa.*", "BAUSA"),
    (r"^kygo.*", "Kygo"),
    (r"^zartmann.*", "Zartmann"),
    (r"^möwe.*", "MÖWE"),
    (r"^robin\s*schulz.*", "Robin Schulz"),
    (r".*pashanim.*", "Pashanim"),
    (r".*01099.*", "01099"),
    (r".*dante.*", "Dante YN"),
]

# ---------- 3. GENRE-ZUORDNUNG ----------

def normalize_genre(genre: str) -> str:
    genre = genre.strip().lower()
    replacements = {
        "hiphop": "Hip-Hop",
        "hip hop": "Hip-Hop",
        "hip-hop": "Hip-Hop",
        "rap": "Rap",
        "trap": "Trap",
        "pop": "Pop",
        "dance": "Dance",
        "tropical house": "Tropical House",
        "deep house": "Deep House",
        "house": "House",
    }
    return replacements.get(genre, genre.title())

RAW_GENRE_MAP = {
    "makko": "hiphop",
    "zartmann": "pop",
    "01099": "hip hop",
    "pashanim": "hip hop",
    "dante yn": "hip hop",
    "kygo": "tropical house",
    "möwe": "deep house",
    "robin schulz": "dance",
    "2pac": "hip-hop",
    "ski aggu": "hip-hop",
    "max giesinger": "pop",
    "lea": "pop",
    "bausa": "hip-hop",
    "sido": "hiphop",
    "badchieff": "hip-hop",
    "drake": "rap",
    "wiz khalifa": "hiphop",
    "travis scott": "trap",
}

GENRE_MAP = {
    artist.lower(): normalize_genre(genre)
    for artist, genre in RAW_GENRE_MAP.items()
}

# ---------- 4. OPTIONAL: GENRE ZU ARTIST MAP ----------

def get_genre_artist_map() -> dict[str, list[str]]:
    grouped = defaultdict(list)
    for artist, genre in GENRE_MAP.items():
        grouped[genre].append(artist)
    return dict(grouped)