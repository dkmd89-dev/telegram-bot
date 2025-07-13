# -*- coding: utf-8 -*-
"""
Modul zur Normalisierung von Künstlernamen für Musikdaten aus YouTube.

Dieses Skript enthält:
1. Explizite Überschreibungen für bestimmte Künstlernamen
2. Regex-Regeln zur automatischen Bereinigung von YouTube-spezifischen Künstlernamen
3. Erweiterte Logging-Funktionalität
4. Die neuen Regeln sollten **nach den allgemeinen Bereinigungen** (Zeile 9) aber **vor den genre-spezifischen Regeln** eingefügt werden.
"""

import re
import logging
import string
from typing import Dict, List, Tuple

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------- 1. EXPLIZITE KÜNSTLER-ÜBERSCHREIBUNGEN ----------
RAW_OVERRIDES: Dict[str, str] = {
    # Bestehende Künstler
    "makko": "makko",
    "bosse": "Bosse",
    "zartmann": "Zartmann",
    "dante yn": "Dante YN",
    "dante": "Dante YN",
    "kygo": "Kygo",
    "möwe": "MÖWE",
    "mowe": "MÖWE",
    "robin schulz": "Robin Schulz",
    "lea": "LEA",
    "badchieff": "Badchieff",
    "aggu31": "Ski Aggu",
    "ski aggu": "Ski Aggu",
    "bausa": "BAUSA",
    "sido": "Sido",
    "01099": "01099",
    "loredana": "Loredana",
    "bonez mc": "Bonez MC",
    "raf camora": "RAF Camora",
    "raf": "RAF Camora",
    "ufo361": "Ufo361",
    "kool savas": "Kool Savas",
    "187 strassenbande": "187 Strassenbande",
    "gzuz": "Gzuz",
    "lx": "LX",
    "maxwell": "Maxwell",

    # Internationale Künstler
    "1986zig": "1986zig",
    "2pac": "2Pac",
    "tupac": "2Pac",
    "alle farben": "Alle Farben",
    "benson boone": "Benson Boone",
    "böhse onkelz": "Böhse Onkelz",
    "bruno mars": "Bruno Mars",
    "drake": "Drake",
    "travis scott": "Travis Scott",
    "lil baby": "Lil Baby",
    "dj snake": "DJ Snake",
    "dj khaled": "DJ Khaled",
    "t-low": "T-Low",
    "luciano": "Luciano",

    # YouTube-spezifische Einträge
    "official music video": "",
    "lyrics video": "",
    "vevo": "",
    "ytb": "",
    "prod. by": "ft.",
    "prod by": "ft.",
    "ft": "ft.",
    "feat": "feat.",
    "w/": "with"
}

ARTIST_OVERRIDES: Dict[str, str] = {k.lower(): v for k, v in RAW_OVERRIDES.items()}

# ---------- 2. REGEX-REGELN ----------
ARTIST_RULES: List[Tuple[str, str]] = [
    # YouTube-spezifische Bereinigungen (zuerst anwenden)
    (r"^(.+?)\s*-\s*.+", r"\1"),          # Alles nach " - " entfernen
    (r"\[.*?\]", ""),                      # [Klammern] entfernen
    (r"\(.*?\)", ""),                      # (Klammern) entfernen
    (r"\bofficial\b", "", re.IGNORECASE),  # "official" entfernen
    (r"\bvideo\b", "", re.IGNORECASE),     # "video" entfernen
    
    # Feature- und Kollaborationsformate
    (r"\s*\(feat\..*?\)", ""),            # (feat. ...)
    (r"\s*\(ft\..*?\)", ""),              # (ft. ...)
    (r"\s*featuring\s*.*", ""),           # featuring ...
    (r"\s*[\+\&]\s*", ", "),              # + oder & → Komma
    (r"\s*vs\.?\s*", ", "),               # vs oder vs. → Komma
    (r"\s*x\s*", ", "),                   # x → Komma
    (r"\s*with\s+", ", "),                # with → Komma
    (r"\s*\/\s*", ", "),                  # / → Komma
    (r"\s*;\s*", ", "),                   # ; → Komma
    
    # Allgemeine Bereinigungen
    (r"\s*,\s*", ", "),                   # Kommas normalisieren
    (r"\s*-\s*", " "),                    # Bindestriche → Leerzeichen
    (r"\s*'\s*", "'"),                    # Apostrophe bereinigen
    (r"\s*\.\s*", "."),                   # Punkte bereinigen
    (r"^\s+|\s+$", ""),                   # Leerzeichen trimmen
    (r"\s+", " "),                        # Mehrfach-Leerzeichen
    
    # Spezifische Künstler-Regex (nützlich, wenn der Name Teil eines längeren Strings ist)
    # Deutschrap
    (r".*aggu.*", "Ski Aggu"),
    (r".*badchieff.*", "Badchieff"),
    (r".*bausa.*", "BAUSA"),
    (r".*bonez\s*mc.*", "Bonez MC"),
    (r".*dante\s*yn.*", "Dante YN"),
    (r".*sido.*", "Sido"),
    (r".*01099.*", "01099"),
    (r".*pashanim.*", "Pashanim"),
    (r".*loredana.*", "Loredana"),
    (r".*raf\s*camora.*", "RAF Camora"),
    (r".*ufo\s*361.*", "Ufo361"),
    (r".*kool\s*savas.*", "Kool Savas"),
    (r".*187\s*strassenbande.*", "187 Strassenbande"),
    (r".*gzuz.*", "Gzuz"),
    (r".*lx.*", "LX"),
    (r".*maxwell.*", "Maxwell"),
    (r".*nina\s*chuba.*", "Nina Chuba"),
    (r".*sierra\s*kidd.*", "Sierra Kidd"),
    (r".*montez.*", "MONTEZ"),
    (r".*kraftklub.*", "KRAFTKLUB"),
    (r".*ak\s*ausserkontrolle.*", "AK Ausserkontrolle"),
	(r".*capital\s*bra.*", "Capital Bra"),
	(r".*fler.*", "Fler"),
	(r".*kollegah.*", "Kollegah"),
	(r".*farid\s*bang.*", "Farid Bang"),
	(r".*samra.*", "Samra"),
	(r".*luciano.*", "Luciano"),
	(r".*kontra\s*k.*", "Kontra K"),
	(r".*summer\s*cem.*", "Summer Cem"),
	(r".*majoe.*", "Majoe"),
	(r".*joker\s*bra.*", "Joker Bra"),
	(r".*kalim.*", "Kalim"),
	(r".*reezy.*", "Reezy"),
	(r".*kanye\s*west.*", "Kanye West"),
	(r".*the\s*carters.*", "The Carters"),
	(r".*jay\s*z.*", "Jay-Z"),
	(r".*capital\s?bra.*", "Capital Bra"),  # Match mit/ohne Leerzeichen
	(r".*kanye\s?west.*", "Kanye West"),
	(r".*t\s?low.*", "T-Low")  # Für "T Low", "T-Low", "Tlow"
	
    # Pop / Andere
    (r".*bosse.*", "Bosse"),
    (r".*lea.*", "LEA"),
    (r".*kygo.*", "Kygo"),
    (r".*zartmann.*", "Zartmann"),
    (r".*möwe.*", "MÖWE"),
    (r".*robin\s*schulz.*", "Robin Schulz"),
    (r".*johannes\s*oerding.*", "Johannes Oerding"),
    (r".*max\s*giesinger.*", "Max Giesinger"),
    (r".*silbermond.*", "Silbermond"),
    (r".*seeed.*", "Seeed"),
    (r".*alle\s*farben.*", "Alle Farben"),
    (r".*benson\s*boone.*", "Benson Boone"),
    (r".*the\s*weeknd.*", "The Weeknd"),
	(r".*post\s*malone.*", "Post Malone"),
	(r".*ariana\s*grande.*", "Ariana Grande"),
	(r".*taylor\s*swift.*", "Taylor Swift"),
	(r".*ed\s*sheeran.*", "Ed Sheeran"),
	(r".*billie\s*eilish.*", "Billie Eilish"),
	(r".*doja\s*cat.*", "Doja Cat"),
	(r".*david\s*guetta.*", "David Guetta"),
	(r".*calvin\s*harris.*", "Calvin Harris"),
	(r".*martin\s*garrix.*", "Martin Garrix"),
	(r".*tiesto.*", "Tiësto"),
	(r".*marshmello.*", "Marshmello"),
	(r".*dualipa.*", "Dua Lipa"),

    # International
    (r".*travis\s*scott.*", "Travis Scott"),
    (r".*bruno\s*mars.*", "Bruno Mars"),
    (r".*drake.*", "Drake"),
    (r".*2pac.*|.*tupac.*", "2Pac"),
    (r".*the\s*weeknd.*", "The Weeknd"),
	(r".*post\s*malone.*", "Post Malone"),
	(r".*ariana\s*grande.*", "Ariana Grande"),
	(r".*taylor\s*swift.*", "Taylor Swift"),
	(r".*ed\s*sheeran.*", "Ed Sheeran"),
	(r".*billie\s*eilish.*", "Billie Eilish"),
	(r".*doja\s*cat.*", "Doja Cat"),
	(r".*david\s*guetta.*", "David Guetta"),
	(r".*calvin\s*harris.*", "Calvin Harris"),
	(r".*martin\s*garrix.*", "Martin Garrix"),
	(r".*tiesto.*", "Tiësto"),
	(r".*marshmello.*", "Marshmello"),
	(r".*dualipa.*", "Dua Lipa"),
]

COMPILED_RULES = [(re.compile(pattern, re.IGNORECASE), replacement)
                 for pattern, replacement in ARTIST_RULES]

def clean_artist_name(name: str) -> str:
    """
    Bereinigt und normalisiert einen Künstlernamen aus YouTube-Daten.
    
    Args:
        name (str): Rohname aus YouTube (z.B. "ARTIST - SONG (feat. X) [Video]")
    
    Returns:
        str: Bereinigter Name (z.B. "ARTIST, X")
    """
    original_name = name
    logger.debug(f"Verarbeite YouTube-Künstlername: '{original_name}'")
    
    # Nicht-druckbare Zeichen entfernen
    printable = set(string.printable)
    name = "".join(filter(lambda x: x in printable, name))
    
    # Allgemeine YouTube-Bereinigung
    for pattern, replacement in COMPILED_RULES[:9]:
        name = pattern.sub(replacement, name)
    
    # Explizite Überschreibungen prüfen
    lower_name = name.strip().lower()
    if lower_name in ARTIST_OVERRIDES:
        result = ARTIST_OVERRIDES[lower_name]
        if result == "":  # Falls leer (z.B. bei "official video")
            result = name.strip()
        if original_name != result:
            logger.info(f"Explizite Überschreibung (YouTube): '{original_name}' → '{result}'")
        return result if result else name
    
    # Künstlerspezifische Regeln anwenden
    for pattern, replacement in COMPILED_RULES[9:]:
        if pattern.search(name):
            result = replacement
            if original_name != result:
                logger.info(f"Regex-Regel (YouTube): '{original_name}' → '{result}'")
            return result
    
    # Fallback: Title-Case und endgültige Bereinigung
    result = name.strip().title()
    for pattern, replacement in COMPILED_RULES[9:]:  # Allgemeine Regeln erneut anwenden
        result = pattern.sub(replacement, result)
    
    if result != original_name:
        logger.info(f"Title-Case (YouTube): '{original_name}' → '{result}'")
    else:
        logger.debug(f"Keine Transformation für: '{original_name}'")
    
    return result