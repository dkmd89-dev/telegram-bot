import re
import unicodedata
from logger import log_debug

# Entfernt Präfixe wie Tracknummern oder eckige Klammern
RE_REMOVE_PREFIXES = [
    r"^\d+\s*",              # Tracknummern (z. B. 01 Artist - Title)
    r"^\[.*?\]\s*",          # eckige Klammern am Anfang
    r"^new\s*",              # "new" am Anfang
]

# Entfernt Suffixe wie "(Official Video)", "Lyrics" etc.
RE_REMOVE_SUFFIXES = [
    r"\s*\(official.*?\)",   # (Official Video), (Official Audio), etc.
    r"\s*\[.*?\]$",          # [Live], [Lyrics], etc.
    r"\s*lyrics$",           # "lyrics" am Ende
    r"\s*\(prod.*?\)",       # (prod. by ...)
    r"\s*\(ft.*?\)",         # (ft. ...)
    r"\s*\(feat.*?\)",       # (feat. ...)
    r"\s*HD$",               # "HD" am Ende
]

def clean_input_artist_title(raw_input: str) -> tuple[str, str]:
    """
    Bereinigt Eingabe wie 'Artist - Title [Official Video]' in (artist, title).
    Gibt (artist, title) zurück oder ("", raw_input), wenn kein '-' gefunden wurde.
    """

    original = raw_input
    raw_input = raw_input.strip()

    # Unicode normalisieren (z. B. für seltsame Leerzeichen oder Unicode-Zeichen)
    raw_input = unicodedata.normalize("NFKC", raw_input)

    # Präfixe entfernen
    for pat in RE_REMOVE_PREFIXES:
        raw_input = re.sub(pat, '', raw_input, flags=re.IGNORECASE)

    # Suffixe entfernen
    for pat in RE_REMOVE_SUFFIXES:
        raw_input = re.sub(pat, '', raw_input, flags=re.IGNORECASE)

    # Versuche nach Artist - Title zu trennen
    parts = re.split(r'\s*-\s*', raw_input)
    if len(parts) == 2:
        artist, title = parts[0].strip(), parts[1].strip()
    elif len(parts) > 2:
        artist = parts[0].strip()
        title = ' - '.join(parts[1:]).strip()
    else:
        artist = ""
        title = raw_input.strip()

    log_debug(f"[clean_input_artist_title] Ursprünglich: '{original}' ➜ Artist: '{artist}', Title: '{title}'")
    return artist, title