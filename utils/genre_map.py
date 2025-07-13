# -*- coding: utf-8 -*-
"""
Modul zur Normalisierung von Genre-Namen für Musikdaten.

Dieses Skript enthält:
1. Explizite Überschreibungen für bestimmte Genre-Namen
2. Regex-Regeln zur automatischen Bereinigung und Kategorisierung von Genre-Namen
3. Logging-Funktionalität zur Nachverfolgung von Namensänderungen
"""

import re
import logging
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

# ---------- 1. EXPLIZITE GENRE-ÜBERSCHREIBUNGEN ----------
# Hier können spezifische, oft falsch geschriebene oder abweichende Genre-Namen
# direkt einem standardisierten Genre zugeordnet werden.
# Schlüssel sollten in Kleinbuchstaben sein, um die Prüfung zu vereinfachen.

RAW_OVERRIDES: Dict[str, str] = {
    # Allgemeine Abkürzungen und Varianten
    "hiphop": "Hip Hop",
    "rnb": "R&B",
    "rocknroll": "Rock",
    "edm": "Electronic",
    "electronic dance music": "Electronic",
    "dnb": "Drum & Bass", # Spezifischer als nur Electronic
    "drum and bass": "Drum & Bass",
    "techno": "Electronic",
    "house": "Electronic",
    "trance": "Electronic",
    "electro": "Electronic",
    "chillout": "Electronic",
    "dance": "Electronic",
    "dubstep": "Electronic",
    "trap": "Hip Hop",
    "deutschrap": "Hip Hop",
    "german rap": "Hip Hop",
    "pop-rock": "Pop", # Wenn Pop die primäre Zuordnung sein soll
    "alternative rock": "Rock",
    "hard rock": "Rock",
    "heavy metal": "Metal",
    "punk rock": "Punk",
    "folk rock": "Folk",
    "indie rock": "Indie",
    "country rock": "Country",
    "latin pop": "Latin",
    "k-pop": "K-Pop",
    "j-pop": "J-Pop",
    "soundtrack": "Soundtrack",
    "film score": "Soundtrack",
    "classical": "Klassik",
    "christmas": "Weihnachten",
    "holiday": "Weihnachten",
    "schlager": "Schlager",
    "volksmusik": "Volksmusik",
    "world music": "Weltmusik",
    "ambient": "Electronic",
    "lo-fi": "Lo-Fi",
    "jazz fusion": "Jazz",
    "blues rock": "Blues",
    "gospel": "Gospel",
    "soul": "Soul",
    "funk": "Funk",
    "disco": "Disco",
    "reggae": "Reggae",
    "ska": "Ska",
    "punk": "Punk",
    "metal": "Metal",
    "blues": "Blues",
    "country": "Country",
    "folk": "Folk",
    "jazz": "Jazz",
    "pop": "Pop",
    "rock": "Rock",
    "hip hop": "Hip Hop",
    "r&b": "R&B",
    "latin": "Latin",
    "gothic": "Gothic",
    "new age": "New Age",
    "children's music": "Kindermusik",
    "spoken word": "Spoken Word",
    "comedy": "Comedy",
    "audiobook": "Hörbuch", # Nicht unbedingt ein Musikgenre, aber nützlich
    "podcast": "Podcast", # Nicht unbedingt ein Musikgenre, aber nützlich
    "sound effects": "Soundeffekte", # Nicht unbedingt ein Musikgenre, aber nützlich
}

GENRE_OVERRIDES: Dict[str, str] = {k.lower(): v for k, v in RAW_OVERRIDES.items()}

# ---------- 2. REGEX-REGELN ZUR GENRE-BEREINIGUNG UND ZUORDNUNG ----------
# Diese Regeln werden angewendet, um unerwünschte Zusätze zu entfernen
# und Sub-Genres oder ähnliche Begriffe einem Haupt-Genre zuzuordnen.
# Die Reihenfolge ist wichtig: Allgemeine Bereinigungen zuerst, dann spezifische Zuordnungen.

GENRE_RULES: List[Tuple[str, str]] = [
    # 1. Allgemeine Bereinigungen (entfernen von Zusatzinformationen)
    # Entfernt alles in Klammern oder eckigen Klammern, das typische Genre-Zusätze enthält.
    # Z.B. "(Mix)", "[Live]", "(Radio Edit)"
    (r"\s*(\(|\[)(mix|remix|edit|version|live|radio|official|instrumental|acoustic|cover|bootleg|mashup|playlist|compilation|hits|best of|vol\.\s*\d+|part\s*\d+|chapter\s*\d+)\b[^)]*?(\)|\])", ""),
    # Entfernt gängige Trennzeichen und Zusätze wie " / ", " | ", " & " wenn sie Genres trennen
    (r"\s*[/|&]\s*", ", "),
    # Entfernt Begriffe wie "Music", "Songs", "Tracks" wenn sie am Ende stehen
    (r"\s*(music|songs|tracks|genre|style)\s*$", ""),
    # Entfernt führende/abschließende Bindestriche oder Leerzeichen
    (r"^\s*[-,\s]+|[-,\s]+\s*$", ""),
    # Normalisiert Leerzeichen und Kommas
    (r"\s*,\s*", ", "),
    (r",+", ","),
    (r"\s+", " "),
    (r"^\s+|\s+$", ""), # Trimmt führende/abschließende Leerzeichen

    # 2. Spezifische Genre-Zuordnungen (von spezifisch zu allgemeiner)
    # Diese Regeln überschreiben nicht, sondern ordnen zu, wenn das Muster gefunden wird.
    # Die Reihenfolge ist wichtig: spezifischere Matches sollten vor allgemeineren stehen.
    (r".*drum\s*&?\s*bass.*", "Drum & Bass"),
    (r".*dnb.*", "Drum & Bass"),
    (r".*dubstep.*", "Electronic"),
    (r".*trap.*", "Hip Hop"),
    (r".*deutschrap.*", "Hip Hop"),
    (r".*german\s*rap.*", "Hip Hop"),
    (r".*k-pop.*", "K-Pop"),
    (r".*j-pop.*", "J-Pop"),
    (r".*r&b.*", "R&B"),
    (r".*rnb.*", "R&B"),
    (r".*hip\s*hop.*", "Hip Hop"),
    (r".*rap.*", "Hip Hop"), # Sollte nach spezifischeren Rap-Varianten kommen
    (r".*house.*", "Electronic"),
    (r".*techno.*", "Electronic"),
    (r".*trance.*", "Electronic"),
    (r".*electro.*", "Electronic"),
    (r".*chillout.*", "Electronic"),
    (r".*dance.*", "Electronic"),
    (r".*ambient.*", "Electronic"),
    (r".*lo-fi.*", "Lo-Fi"),
    (r".*electronic.*", "Electronic"), # Muss nach allen spezifischeren Electronic-Subgenres kommen
    (r".*metal.*", "Metal"),
    (r".*punk.*", "Punk"),
    (r".*hard\s*rock.*", "Rock"),
    (r".*alternative\s*rock.*", "Rock"),
    (r".*folk\s*rock.*", "Folk"),
    (r".*indie\s*rock.*", "Indie"),
    (r".*rock.*", "Rock"), # Muss nach allen spezifischeren Rock-Subgenres kommen
    (r".*pop.*", "Pop"),
    (r".*soundtrack.*", "Soundtrack"),
    (r".*film\s*score.*", "Soundtrack"),
    (r".*classical.*", "Klassik"),
    (r".*klassik.*", "Klassik"),
    (r".*christmas.*", "Weihnachten"),
    (r".*holiday.*", "Weihnachten"),
    (r".*schlager.*", "Schlager"),
    (r".*volksmusik.*", "Volksmusik"),
    (r".*world\s*music.*", "Weltmusik"),
    (r".*jazz.*", "Jazz"),
    (r".*blues.*", "Blues"),
    (r".*country.*", "Country"),
    (r".*folk.*", "Folk"),
    (r".*soul.*", "Soul"),
    (r".*funk.*", "Funk"),
    (r".*disco.*", "Disco"),
    (r".*reggae.*", "Reggae"),
    (r".*ska.*", "Ska"),
    (r".*latin.*", "Latin"),
    (r".*gothic.*", "Gothic"),
    (r".*new\s*age.*", "New Age"),
    (r".*children's\s*music.*", "Kindermusik"),
    (r".*spoken\s*word.*", "Spoken Word"),
    (r".*comedy.*", "Comedy"),
    (r".*audiobook.*", "Hörbuch"),
    (r".*podcast.*", "Podcast"),
    (r".*sound\s*effects.*", "Soundeffekte"),
]

# Vorcompilierte Regex-Patterns für bessere Performance
# re.IGNORECASE wird verwendet, um Groß- und Kleinschreibung zu ignorieren.
COMPILED_RULES = [(re.compile(pattern, re.IGNORECASE), replacement) 
                 for pattern, replacement in GENRE_RULES]

def clean_genre_name(name: str) -> str:
    """
    Bereinigt und normalisiert einen Genre-Namen anhand definierter Regeln.
    
    Args:
        name (str): Der zu bereinigende Genre-Name
        
    Returns:
        str: Der bereinigte und normalisierte Genre-Name
    
    Verarbeitungsschritte:
        1. Entfernen von Leerzeichen am Anfang/Ende und Umwandlung in Kleinbuchstaben
        2. Prüfung auf explizite Überschreibungen (höchste Priorität)
        3. Anwendung der Regex-Bereinigungsregeln (mehrere können angewendet werden)
        4. Anwendung der Regex-Zuordnungsregeln (die erste passende wird angewendet)
        5. Falls keine Regel zutrifft: Title-Case als Fallback oder ein Standard-Genre.
    """
    original_name = name
    name = name.strip()
    lower_name = name.lower()
    
    logger.debug(f"Verarbeite Genre-Name: '{original_name}'")
    
    # 1. Prüfe explizite Überschreibungen (höchste Priorität)
    if lower_name in GENRE_OVERRIDES:
        result = GENRE_OVERRIDES[lower_name]
        logger.info(f"Explizite Überschreibung: '{original_name}' → '{result}'")
        return result
    
    # Temporäre Variable für die Bereinigung, da mehrere Bereinigungsregeln greifen können
    cleaned_name = name 
    
    # 2. Wende Regex-Regeln an
    for pattern, replacement in COMPILED_RULES:
        # Prüfe, ob es eine Bereinigungsregel ist (replacement ist leer)
        # oder eine spezifische Genre-Zuordnungsregel.
        if pattern.search(cleaned_name):
            if replacement == "": # Dies ist eine Bereinigungsregel
                # Wende die Bereinigung an und fahre mit dem bereinigten Namen fort
                cleaned_name = pattern.sub(replacement, cleaned_name).strip()
                logger.debug(f"Bereinigungsregel angewendet: '{original_name}' (aktuell: '{cleaned_name}') durch Pattern '{pattern.pattern}'")
            else: # Dies ist eine spezifische Genre-Zuordnungsregel
                # Die erste passende Zuordnungsregel wird angewendet und zurückgegeben
                result = replacement
                logger.info(f"Spezifische Genre-Regel angewendet: '{original_name}' → '{result}' (Pattern: {pattern.pattern})")
                return result
    
    # 3. Fallback: Wenn keine Regel zutrifft, verwende den (bereinigten) Namen im Title-Case.
    # Wenn der bereinigte Name leer ist, setze auf "Unbekannt".
    result = cleaned_name.title() if cleaned_name else "Unbekannt"
    
    if result != original_name:
        logger.info(f"Fallback/Title-Case angewendet: '{original_name}' → '{result}'")
    else:
        logger.debug(f"Keine Transformationen angewendet auf: '{original_name}'")
    
    return result
