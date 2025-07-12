# genre_config.py

# 🎧 Genre-Korrekturen und Prioritäten

GENRE_MAP = {
    # Hip-Hop / Rap
    "hip hop": "Hip-Hop",
    "hiphop": "Hip-Hop",
    "hip-hop": "Hip-Hop",
    "rap": "Rap",
    "deutschrap": "Deutschrap",
    "german rap": "Deutschrap",
    "trap": "Trap",
    "emo rap": "Rap",
    "cloud rap": "Rap",

    # Pop
    "pop": "Pop",
    "synthpop": "Pop",
    "electropop": "Pop",
    "dance pop": "Pop",
    "indie pop": "Pop",
    "teen pop": "Pop",
    "german pop": "Pop",

    # Rock
    "rock": "Rock",
    "pop rock": "Rock",
    "punk rock": "Rock",
    "alternative rock": "Rock",
    "indie rock": "Rock",
    "classic rock": "Rock",
    "hard rock": "Rock",
    "soft rock": "Rock",
    "garage rock": "Rock",
    "metal": "Rock",
    "heavy metal": "Rock",
    "nu metal": "Rock",
    "emo": "Rock",

    # Electronic
    "electronic": "Electronic",
    "electronica": "Electronic",
    "electro": "Electronic",
    "idm": "Electronic",
    "downtempo": "Downtempo",
    "ambient": "Electronic",
    "edm": "Electronic",
    "dnb": "Electronic",
    "drum and bass": "Electronic",
    "techno": "Techno",
    "deep techno": "Techno",
    "hard techno": "Techno",
    "minimal techno": "Techno",
    "house": "House",
    "deep house": "House",
    "progressive house": "House",
    "tech house": "House",
    "trance": "Electronic",
    "psytrance": "Electronic",
    "fullon": "Electronic",
    "goa": "Electronic",

    # Jazz / Soul / Funk
    "jazz": "Jazz",
    "smooth jazz": "Jazz",
    "vocal jazz": "Jazz",
    "funk": "Jazz",
    "soul": "Jazz",
    "neo soul": "Jazz",
    "rnb": "Jazz",
    "r&b": "Jazz",

    # Classical
    "classical": "Classical",
    "orchestral": "Classical",
    "baroque": "Classical",
    "romantic": "Classical",
    "modern classical": "Classical",
    "opera": "Classical",

    # Weltmusik & Folk
    "folk": "Folk",
    "indie folk": "Folk",
    "world": "World",
    "world music": "World",
    "afrobeat": "World",
    "balkan": "World",
    "ethnic": "World",

    # Deutschsprachig
    "schlager": "Schlager",
    "volkst\u00fcmlich": "Schlager",
    "deutschpop": "Pop",
    "deutsch rock": "Rock",
    "ndw": "Pop",

    # Soundtrack & Co
    "soundtrack": "Soundtrack",
    "soundtracks": "Soundtrack",
    "film score": "Soundtrack",
    "musical": "Soundtrack",
    "instrumental": "Other",
    "spoken word": "Other",
    "karaoke": "Other",

    # Schlechte / allgemeine Begriffe
    "none": "Other",
    "unknown": "Other",
    "unbekannt": "Other",
    "no genre": "Other",
    "test": "Other",
    "default": "Other",
    "various": "Other",
    "random": "Other",
    "mix": "Other",
    "audio": "Other",
    "songs": "Pop",
    "music": "Pop",
    "musik": "Pop",
    "female": "Other",
    "germany": "Pop",
    "favorites": "Pop",
    "awesome": "Pop",
    "s artist": "Other",
    "feat": "Other",
    "featuring": "Other",
    "intro": "Other",
    "single": "Other",
    "cover": "Pop",
}

GENRE_PRIORITY = [
    "Deutschrap", "Hip-Hop", "Rap", "Trap",
    "Pop", "Rock", "Indie", "Electronic", "House", "Techno", "Downtempo",
    "Jazz", "Classical", "Folk", "World", "Schlager",
    "Soundtrack", "Other"
]

METADATA_DEFAULTS = {
    "genre": "Other"
}  # Für Fallbacks in der Genre-Auswahl
