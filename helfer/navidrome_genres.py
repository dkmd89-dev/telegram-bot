# -*- coding: utf-8 -*-
# yt_music_bot/helfer/navidrome_genres.py
"""
Navidrome Genre-Statistik Tool
"""
import argparse
from config import Config
import logging
from typing import Union, Optional, List, Dict, Any

# Importiere die relevanten Funktionen und Konfigurationen aus genre_helfer.py
from helfer.genre_helfer import ( #
    get_navidrome_genres, #
    setup_logger, #
)

# Logger einrichten
# Verwenden Sie den setup_logger aus genre_helfer.py für Konsistenz
logger = setup_logger("navidrome_genres", Config.LOG_DIR / "genre_handler.log") #


def main():
    parser = argparse.ArgumentParser(description="📊 Navidrome Genre-Statistiken")
    parser.add_argument(
        "--sort-by",
        type=str,
        choices=["songs", "name"],
        default="songs",
        help="Sortierkriterium: 'songs' (nach Anzahl der Songs) oder 'name' (alphabetisch). Standard: songs",
    )
    parser.add_argument(
        "--min-songs",
        type=int,
        default=0,
        help="Mindestanzahl an Songs, die ein Genre haben muss, um angezeigt zu werden. Standard: 0",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limitiert die Ausgabe auf die Top-N-Ergebnisse. Standard: Keine Limitierung",
    )
    args = parser.parse_args()

    # Rufe die get_navidrome_genres Funktion aus genre_helfer.py auf
    # Diese Funktion gibt entweder eine Liste von Genres oder eine Fehlermeldung zurück.
    result = get_navidrome_genres(sort_by=args.sort_by, min_songs=args.min_songs, limit=args.limit) #

    if isinstance(result, str):
        # Wenn result ein String ist, handelt es sich um eine Fehlermeldung
        logger.error(f"Fehler beim Abrufen der Genres: {result}") #
        print(f"Fehler: {result}")
    else:
        # Andernfalls ist es eine Liste von Genres
        if not result:
            logger.info("Keine Genres gefunden, die den Kriterien entsprechen.") #
            print("Keine Genres gefunden, die den Kriterien entsprechen.")
            return

        print(f"\n--- Top Navidrome Genres (sortiert nach {args.sort_by}) ---")
        for genre_info in result:
            genre_name = genre_info.get("value", "N/A")
            song_count = genre_info.get("songCount", 0)
            print(f"- {genre_name}: {song_count} Songs")
        logger.info(f"Erfolgreich {len(result)} Genres angezeigt.") #


if __name__ == "__main__":
    main()