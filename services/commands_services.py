# commands_services.py
# -*- coding: utf-8 -*-
"""
Definiert Befehls-Kategorien und Beschreibungen für den Telegram-Bot.
Wird von command_handler.py, button_handler.py etc. importiert.
"""

from emoji import EMOJI
from helfer.markdown_helfer import escape_md_v2

# --- Vollständige Befehls-Kategorien mit Emojis ---
COMMAND_CATEGORIES = {
    "📚 Navidrome": {
        "📂 Medien": ["artists", "indexes", "albumlist", "genres"],
        "📂 Bibliothek": ["navidrome", "scan"],
        "📊 Playstatistiken": ["topsongs", "topsongs7", "topartists", "monthreview", "yearreview"],
        "🎧 Aktivität": ["playing", "lastplayed"]
    },
    "🛠️ Wartung & Korrektur": {
        "🖼️ Cover": ["fixcovers", "fixlyrics"],  # Replaced fixcoverslyrics with fixlyrics
        "🎶 Genres": ["fixgenres", "rescan_genres"]
    },
    "▶️ YouTube Befehle": ["download"],
    "⚙️ System & Hilfe": ["status", "backup", "help"]
}

# --- Vollständige Befehlsbeschreibungen mit Emojis ---
COMMAND_DESCRIPTIONS = {
    # Navidrome Befehle
    "navidrome": f"{EMOJI['navidrome']} Zeigt Navidrome Bibliotheksstatistiken (Alben, Songs, Genres)",
    "scan": f"{EMOJI['scan']} Startet manuellen Navidrome Bibliotheks-Scan",
    "genres": f"{EMOJI['genres']} Zeigt alle Genres in der Navidrome-Bibliothek",
    "artists": f"{EMOJI['artist']} Listet alle Künstler alphabetisch gruppiert",
    "indexes": f"{EMOJI['album']} Listet alphabetisch sortierte Künstler und Alben",
    "albumlist": f"{EMOJI['album']} Listet Alben nach Kriterien (Neueste, Beliebte, Zufällig, Höchstbewertet, Alphabetisch)",

    # Wartung & Korrektur
    "fixcovers": f"{EMOJI['fixcovers']} Behebt fehlende Albumcover in Musikdateien",
    "fixlyrics": f"{EMOJI['fixcovers']} Behebt fehlende Songtexte in Musikdateien mit der Genius API",  # New description
    "fixgenres": f"{EMOJI['fixgenres']} Korrigiert fehlende oder inkorrekte Genre-Tags in Musikdateien",
    "rescan_genres": f"{EMOJI['rescan_genres']} Führt einen vollständigen Rescan der Genre-Tags aller Musikdateien durch",
    "testapi": f"{EMOJI['system']} Testet die Navidrome API-Verbindung",

    # Playstatistiken
    "topsongs": f"{EMOJI['topsongs']} Top 10 Songs (30 Tage)",
    "topsongs7": f"{EMOJI['topsongs']} Top 10 Songs (7 Tage)",
    "topartists": f"{EMOJI['topartists']} Top 10 Künstler (30 Tage)",
    "monthreview": f"{EMOJI['calendar']} Monatsrückblick deiner Hörgewohnheiten",
    "yearreview": f"{EMOJI['trophy']} Jahresstatistik mit Highlights",
    "playing": f"{EMOJI['now_playing']} Zeigt den aktuell in Navidrome wiedergegebenen Titel an",
    "lastplayed": f"{EMOJI['lastplayed']} Zeigt den zuletzt gehörten Song in Navidrome an",

    # YouTube
    "download": f"{EMOJI['download']} Lädt YouTube-Videos als Audio herunter",

    # System
    "status": f"{EMOJI['status']} Zeigt Systemstatus & Ressourcen-Auslastung an",
    "backup": f"{EMOJI['backup']} Erstellt ein vollständiges Backup des Musikordners",
    "help": f"{EMOJI['help']} Zeigt diese Hilfe und alle verfügbaren Befehle an"
}