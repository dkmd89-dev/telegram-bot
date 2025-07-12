import re
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path
from config import Config  # Import aus separater config.py

class TitleCleaner:
    _logger_initialized = False

    @classmethod
    def _init_logger(cls):
        if not cls._logger_initialized:
            # Logger konfigurieren
            cls.logger = logging.getLogger("TitleCleaner")
            cls.logger.setLevel(logging.DEBUG)
            
            # Log-Verzeichnis sicher erstellen
            Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
            
            # Log-Datei mit Datumsstempel
            log_file = Config.LOG_DIR / f"title_cleaner_{datetime.now().strftime('%Y-%m-%d')}.log"
            
            # FileHandler mit UTF-8 Encoding
            handler = logging.FileHandler(log_file, encoding='utf-8')
            handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s'
            ))
            
            cls.logger.addHandler(handler)
            cls._logger_initialized = True

    @staticmethod
    def clean_title(raw_title: str, artist: Optional[str] = None) -> str:
        """Bereinigt Musiktitel mit smarter Co-Artist-Entfernung & Logging."""
        TitleCleaner._init_logger()
        logger = TitleCleaner.logger
    
        if not raw_title:
            logger.warning("Empty title received")
            return ""
    
        original = raw_title.strip()
        cleaned = original
        logger.debug(f"Original: '{original}'")
    
        # 1. Entferne (feat...), [feat...], etc.
        cleaned = re.sub(r"(?i)[\(\[]?\s*(feat\.?|ft\.?|featuring)\s+[^\)\]]+[\)\]]?", "", cleaned).strip()
        logger.debug(f"After feat./ft. removal: '{cleaned}'")
    
        # 2. Entferne führenden Artist, falls bekannt
        if artist:
            pattern = rf"(?i)^{re.escape(artist.strip())}\s*[-–—|:]*\s*"
            cleaned = re.sub(pattern, "", cleaned).strip()
            logger.debug(f"After artist prefix removal: '{cleaned}'")
    
        # 3. Entferne evtl. weiteren Artist am Anfang (z. B. HAYLA – Title)
        cleaned = re.sub(r"(?i)^([A-ZÄÖÜa-z0-9& .,'\"!?]{1,30})\s*[-–—|:]+\s*", "", cleaned).strip()
        logger.debug(f"After possible leading co-artist removal: '{cleaned}'")
    
        # 4. Vereinheitliche Trennzeichen & Leerzeichen
        cleaned = re.sub(r"\s*[-–—|:]+\s*", " - ", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -")
        logger.debug(f"After separator normalization: '{cleaned}'")
    
        # 5. Entferne sonstige Inhalte in Klammern wie (Official Video), [Live], (Audio)
        cleaned = re.sub(r"(?i)[\(\[].*?[\)\]]", "", cleaned).strip()
        logger.debug(f"After bracket content removal: '{cleaned}'")
    
        # 6. Entferne typische YouTube-Zusätze
        cleaned = re.sub(r"(?i)\b(official|video|audio|visualizer|lyrics?|HD|remastered|live( at)? .*)\b", "", cleaned).strip()
        logger.debug(f"After YouTube suffix cleanup: '{cleaned}'")

        # 7. Entferne spezifische, nicht-musikalische Metadaten (TV-Shows, Daten, Sender)
        # Passen Sie diese Regex an die häufigsten unerwünschten Muster in Ihren Dateinamen an.
        # Hier ein Beispiel für das Muster "Che tempo che fa", Daten und "Rai".
        cleaned = re.sub(r"(?i)\s*(Che\s+tempo\s+che\s+fa|Rai|\d{1,2}\s+\d{1,2}\s+\d{4}|radio\s+edit|live\s+at)\s*", "", cleaned).strip()
        logger.debug(f"After specific metadata cleanup: '{cleaned}'")
    
        # 8. Letzte Leerzeichen-Bereinigung
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -")
        result = cleaned or original
    
        logger.info(f"Cleaned '{original}' → '{result}'")
        return result