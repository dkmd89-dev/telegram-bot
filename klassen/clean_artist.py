# klassen/clean_artist.py

import re
from logger import log_debug
from klassen.artist_map import ARTIST_RULES, ARTIST_OVERRIDES

class CleanArtist:
    def __init__(self):
        self.rules = ARTIST_RULES
        self.overrides = ARTIST_OVERRIDES

    def clean(self, name: str) -> str:
        """Bereinigt und normalisiert einen K¨¹nstlernamen anhand definierter Regeln und Overrides."""
        original = name
        name = name.strip().lower()

        # Regex-Regeln anwenden
        for pattern, replacement in self.rules.items():
            name = re.sub(pattern, replacement, name, flags=re.IGNORECASE)

        # Overrides anwenden
        if name in self.overrides:
            name = self.overrides[name]

        cleaned = name.strip().title()

        log_debug(f"”9À6 Artist-Bereinigung: '{original}' ¡ú '{cleaned}'")
        return cleaned