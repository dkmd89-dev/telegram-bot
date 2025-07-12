import re
import logging
from typing import Optional
from pathlib import Path
from datetime import datetime
from config import Config  # Annahme: Config enthält LOG_DIR etc.

class CleanArtist:
    _logger_initialized = False

    def __init__(self, artist_rules: dict, artist_overrides: dict):
        self.artist_rules = artist_rules
        self.artist_overrides = artist_overrides
        self._init_logger()

    @classmethod
    def _init_logger(cls):
        if not cls._logger_initialized:
            cls.logger = logging.getLogger("CleanArtist")
            cls.logger.setLevel(logging.DEBUG)
            
            Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_file = Config.LOG_DIR / f"clean_artist_{datetime.now().strftime('%Y-%m-%d')}.log"
            
            handler = logging.FileHandler(log_file, encoding='utf-8')
            handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s'
            ))
            
            cls.logger.addHandler(handler)
            cls._logger_initialized = True

    def clean(self, input_artist: str) -> str:
        """Bereinigt einen Artist-Namen mit Logging und kombinierten Regeln."""
        if not input_artist:
            self.logger.warning("Empty artist input received")
            return "Unbekannter Künstler"

        original = input_artist.strip()
        artist = original
        self.logger.debug(f"Original artist: '{original}'")

        # 1. Titel-Trenner entfernen (z.B. " - Topic" bei YouTube)
        artist = re.split(r"\s*[-–—]\s*", artist)[0]
        self.logger.debug(f"After title separator removal: '{artist}'")

        # 2. Override-Prüfung (case-insensitive)
        lower_artist = artist.lower()
        if lower_artist in self.artist_overrides:
            override = self.artist_overrides[lower_artist]
            self.logger.info(f"Override applied: '{artist}' → '{override}'")
            return override

        # 3. Regex-Regeln anwenden
        for pattern, replacement in self.artist_rules.items():
            new_artist = re.sub(pattern, replacement, artist, flags=re.IGNORECASE).strip()
            if new_artist != artist:
                self.logger.debug(f"Rule '{pattern}' applied: '{artist}' → '{new_artist}'")
                artist = new_artist

        # 4. Erneute Override-Prüfung nach Regex
        lower_artist = artist.lower()
        if lower_artist in self.artist_overrides:
            override = self.artist_overrides[lower_artist]
            self.logger.info(f"Post-regex override: '{artist}' → '{override}'")
            return override

        # 5. Multi-Artist-Trennung (feat., &, etc.)
        artist = re.split(r",|\s+&\s+|\s+feat\.?\s+|\s+ft\.?\s+|\s+with\s+", artist, flags=re.IGNORECASE)[0].strip()
        self.logger.debug(f"After multi-artist split: '{artist}'")

        # 6. Sonderzeichen entfernen (dateisystemkompatibel)
        artist = re.sub(r'[<>:"/\\|?*]', '', artist).strip()
        self.logger.debug(f"After special chars removal: '{artist}'")

        # 7. Finale Bereinigung und Fallback
        result = artist or "Unbekannter Künstler"
        self.logger.info(f"Cleaned artist: '{original}' → '{result}'")
        return result


#from artist_map import artist_rules, ARTIST_NAME_OVERRIDES
#from clean_artist import CleanArtist
#get_clean_artist() oder clean_artist_name() durch CleanArtist.clean().
# Initialisierung
# cleaner = CleanArtist(artist_rules=artist_rules, artist_overrides=ARTIST_NAME_OVERRIDES)
#befehl self.artist_cleaner.clean
# Beispielaufrufe
#print(cleaner.clean("Bad Bunny - Topic"))  # → "Bad Bunny"
#print(cleaner.clean("Drake feat. Rihanna"))  # → "Drake"
#print(cleaner.clean("The Weeknd (Official)"))  # → "The Weeknd"



