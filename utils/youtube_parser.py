# -*- coding: utf-8 -*-
"""
Modul zum Parsen von YouTube-Titeln.

Dieses Skript stellt eine Funktion zur Verfügung, um rohe YouTube-Titel
in strukturierte Daten (Künstler, Songtitel) zu zerlegen und von
typischen Zusätzen wie "(Official Video)" zu bereinigen.
"""

import re
import logging
from typing import Dict

# Logging-Konfiguration, falls du detaillierte Ausgaben wünschst
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def parse_youtube_title(title: str) -> Dict[str, str]:
    """
    Zerlegt einen YouTube-Titel in Künstler, Songtitel und entfernt gängige Zusätze.

    Die Funktion versucht, eine klare Trennung zwischen Künstler und Songtitel
    zu finden, die oft durch einen Bindestrich (-) markiert ist.

    Args:
        title (str): Der rohe YouTube-Titel, z.B. "Künstler - Song (Official Video)".

    Returns:
        Dict[str, str]: Ein Dictionary mit den Schlüsseln 'artist', 'song_title'
                        und 'original_title'. 'artist' kann leer sein, wenn keine
                        klare Trennung möglich war.
    """
    if not title:
        return {'artist': '', 'song_title': '', 'original_title': ''}

    original_title = title
    logger.debug(f"Verarbeite Titel: '{original_title}'")

    # 1. Entferne typische Zusätze in Klammern und eckigen Klammern
    # Dies entfernt z.B. (Official Video), [4K], (Lyrics), | prod. by ...
    # Der Regex sucht nach Klammern/eckigen Klammern und allem dazwischen.
    # Auch Zusätze nach einem senkrechten Strich werden entfernt.
    cleaned_title = re.sub(r'\s*(\[|\().*?(\]|\))', '', title)
    cleaned_title = cleaned_title.split('|')[0].strip()
    
    # 2. Versuche, Künstler und Song anhand des Trennzeichens "-" zu trennen
    parts = cleaned_title.split('-', 1)
    
    artist = ""
    song_title = ""

    if len(parts) == 2:
        # Wenn eine Trennung erfolgreich war
        artist = parts[0].strip()
        song_title = parts[1].strip()
        logger.info(f"Titel '{original_title}' getrennt in Künstler '{artist}' und Song '{song_title}'")
    else:
        # Wenn kein Trennzeichen gefunden wurde, nehmen wir an, der ganze
        # bereinigte String ist der Songtitel. Der Künstler müsste dann
        # aus einer anderen Quelle kommen (z.B. Kanalname).
        song_title = cleaned_title
        logger.info(f"Kein Trennzeichen in '{original_title}' gefunden. Songtitel ist '{song_title}'")

    return {
        'artist': artist,
        'song_title': song_title,
        'original_title': original_title
    }

# --- Beispiel für die Anwendung ---
if __name__ == "__main__":
    print("--- Testfälle für den YouTube-Titel-Parser ---")

    test_titles = [
        "Ski Aggu, Sido - Mein Block (Official Video) [4K]",
        "BAUSA - Was du Liebe nennst (Official Music Video)",
        "Peter Fox - Zukunft Pink (feat. Inéz) | Official Video",
        "Alle Farben - Bad Ideas | Official Music Video",
        "Nirvana - Smells Like Teen Spirit (Official Music Video)",
        "Beethovens 9. Symphonie", # Titel ohne klares Trennzeichen
        "Lofi Hip Hop Radio 24/7 📚 chill beats to study/relax to", # Titel mit speziellem Format
        "Travis Scott - SICKO MODE (Audio) ft. Drake", # Feature im Titel
    ]

    for i, test_title in enumerate(test_titles):
        parsed_data = parse_youtube_title(test_title)
        print(f"\n--- Testfall {i+1} ---")
        print(f"Original:     {parsed_data['original_title']}")
        print(f"Erk. Künstler: '{parsed_data['artist']}'")
        print(f"Erk. Song:    '{parsed_data['song_title']}'")

