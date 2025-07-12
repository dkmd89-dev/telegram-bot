# yt_music_bot/config.py
import os
import logging
import lyricsgenius
import musicbrainzngs
from pathlib import Path
from datetime import datetime


class Config:
    # Verzeichniseinstellungen
    BASE_DIR = Path("/mnt/media/musiccenter")
    DOWNLOAD_DIR = BASE_DIR / "import" / "downloads"
    PROCESSED_DIR = BASE_DIR / "import" / "prozess"
    FAIL_DIR = BASE_DIR / "import" / "fail"
    DATA_DIR = BASE_DIR / "cache"
    LIBRARY_DIR = BASE_DIR / "library"
    LOG_DIR = BASE_DIR / "logs"
    ARCHIVE_DIR = BASE_DIR / "import" / "archiv"
    # Pfad zur Datei für den Wiedergabeverlauf
    PLAY_HISTORY_FILE = BASE_DIR / "history" / "play_history.json"
    PLAY_HISTORY_RETENTION_DAYS = 380 # Beispiel: Verlauf für 30 Tage speichern
    # Verzeichnis für generierte Statistikkarten
    STATS_DIR = BASE_DIR / "history" / "stats_charts" # Innerhalb des 'data'-Verzeichnisses
    os.makedirs(STATS_DIR, exist_ok=True) # Stelle sicher, dass dieses Verzeichnis existiert
    

    # Intervall für das automatische Speichern des Wiedergabeverlaufs in Minuten
    PLAY_HISTORY_AUTOSAVE_INTERVAL_MIN = 5 # Beispiel: Alle 5 Minuten speichern

    # API-Tokens:
    BOT_TOKEN = "7415510690:AAFQzEZNAHH63m3Gn9hEJFIGibOlqgGuXqY"
    GENIUS_TOKEN = "EraVZzC6PufXW6DOljKBfck49tZPJh12I_alA8vx2O14psjjQRL0jsk4fL8Lf47r"
    ADMIN_IDS = [490171109]
    ADMIN_CHAT_ID = 490171109  # Ihre Telegram-Chat-ID
    VERSION = "2.0"  # Bot-Version
    

    # Navidrome Konfiguration
    NAVIDROME_URL = "http://romajagijo.zapto.org:4533"  # Ohne trailing slash!
    NAVIDROME_USER = "dkmd"
    NAVIDROME_PASS = "root"
    NAVIDROME_SCAN_TIMEOUT = 45  # Höheren Timeout versuchen
    NAVIDROME_CONTAINER_NAME = "navidrome"  # Oder der tatsächliche Name deines Containers

    # Last.fm Einstellungen
    LASTFM_ENABLED = True
    LASTFM_API_KEY = "64274733df42cd7894e0109f8644545a"
    LASTFM_API_SECRET = "3bfa90688b2760e6829f7473adac265f"
    LASTFM_CACHE_TTL = 3600
    LASTFM_TIMEOUT = 10

    # Audio-Einstellungen
    AUDIO_FORMAT = "m4a"
    AUDIO_FORMAT_STRING = "bestaudio/best"
    AUDIO_QUALITY = "192k"
    MAX_DURATION = 600
    MAX_PLAYLIST_ITEMS = 50
    MAX_FILENAME_LENGTH = 150
    SUPPORTED_FORMATS = (".mp3", ".m4a", ".ogg", ".opus")

    # Playlist-Einstellungen
    PLAYLIST_SETTINGS = {
        "max_single_tracks": 3,
        "max_single_artists": 2,
    }

    # yt-dlp Basisoptionen
    YTDL_BASE_OPTIONS = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": AUDIO_FORMAT,
                "preferredquality": AUDIO_QUALITY,
            }
        ],
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "writethumbnail": True,
        "max_duration": MAX_DURATION,
        "ignoreerrors": True,
        "socket_timeout": 30,
        "retries": 3,
        "extractor_args": {
            "youtube": {
                "player_client": ["web"],
                "skip": ["dash", "hls", "sabr"],
            }
        },
        "audio_multistreams": True,
        "allow_multiple_audio_streams": True,
        "format_sort": [
            "ext:mp3:m4a",
            "acodec:m4a",
            "abr",
        ],
        "no_resize_buffer": True,
        "http_chunk_size": 1048576,
    }

    # Cookie-Datei für Altersbeschränkungen
    COOKIE_FILE = None
    
    # Cover Art Settings
    MAX_COVER_SIZE = 5 * 1024 * 1024  # 5MB max cover size
    COVER_DOWNLOAD_TIMEOUT = 10  # Timeout for cover downloads (seconds)
    COVER_MIN_RESOLUTION = (300, 300)  # Minimum acceptable resolution
    COVER_MAX_RESOLUTION = (1000, 1000)  # Maximum resolution to resize to
    LIBRARY_DIR = Path("/mnt/media/musiccenter/library")
    LOG_DIR = Path("/mnt/media/musiccenter/logs")

    # Genius-Einstellungen
    GENIUS_CONFIG = {
    "fetch_cover_art": True,
    "fetch_lyrics": True,
    "auto_match_threshold": 0.7,
    "rename_files": True,
    "rename_pattern": "{year} - {title}",
    "max_results": 5,
    "retry_attempts": 3,
    "timeout": 15,
    "skip_non_songs": True,
    "remove_section_headers": True,
    }
    GENIUS_TIMEOUT = GENIUS_CONFIG["timeout"]
    GENIUS_ENABLED = GENIUS_CONFIG["fetch_lyrics"] or GENIUS_CONFIG["fetch_cover_art"]

    # MusicBrainz-Einstellungen
    MUSICBRAINZ_ENABLED = True
    MUSICBRAINZ_RETRIES = 2
    MUSICBRAINZ_TIMEOUT = 20
    MUSICBRAINZ_MIN_SIMILARITY = 0.7  # oder ein sinnvoller Wert wie 0.7

    # Standard-Metadaten
    METADATA_DEFAULTS = {
        "genre": None,  # Kein Standard-Genre
        "album": "Single",
        "album_artist": "Artists",
        "year": str(datetime.now().year),
        "track_number": "01",
    }
    DEFAULT_ALBUM_NAME = "Singles"
    UNKNOWN_PLAYLIST = "Unbekannte Playlist"
    MAX_CONCURRENT_DOWNLOADS = 5
    DEBUG_MODE = False

    # Interaktive Tagging-Einstellungen
    INTERACTIVE_TAGGING = {
        "enable_artist_selection": False,
        "enable_album_mode": "auto",
    }

    # Organizer-Einstellungen
    ORGANIZER_CONFIG = {
        "special_dirs": ["Compilations"],
        "filename_sanitize_chars": '<>:"/\\|?*',
        "album_dir_format": "{year} - {album}", # Format für Alben beibehalten
        "single_dir_format": "Singles", # Dies erstellt den Pfad "Artist/Singles/"
        "track_filename_format": "{year} - {title}", # Dateiname soll "Jahr - Titel" sein
        "duplicate_check": True,
        "archive_processed": True,
        "missing_album_log": "missing_album_tags.log",
        "parse_artist_from_filename": True,
        "fallback_artist": "Unknown Artist",
        "artist_collab_patterns": r"\s*(?:&|feat\.?|ft\.?|featuring|vs\.?|x|ū|with|w/|und|mit|pres\.?|presents|,)\s*",
        "filename_patterns": [
            r"^(?P<artist>.+?)\s*-\s*(?P<title>.+?)$",
            r"^\d+\s*-\s*(?P<artist>.+?)\s*-\s*(?P<title>.+?)$",
            r"^\s*(?P<artist>.+?)\s*\s*(?P<title>.+?)$",
            r"^(?P<artist>.+?)\.(?P<title>.+?)$",
        ],
        "filename_rules": {
            r"^.*\s(?:x|feat\.?|ft\.?|featuring|vs\.?|with|w/|&)\s.*?-\s": "",
            r"^.*\s-\s": "",
            r".*?": "",
            r"\s*[-,]\s*$": "",
        },
        "replace_artist_from_title_if": [
            "seven hip-hop",
            "unknown",
            "unknown artist",
            "various",
            "various artists",
            "nobolox",
        ],
    }

        # Artist Name Mapping
    ARTIST_NAME_OVERRIDES = {
    "makko": "makko",
    "maKKo": "makko",
    "MAKKO": "makko",
    "Makko": "makko",
    "BosseA": "Bosse",
    "BosseAxel": "Bosse",
    "bosse": "Bosse",
    "zartmann": "Zartmann",
    "ZARTMANN": "Zartmann",
    "dante": "Dante YN",
    "dante yn": "Dante YN",
    "kygo": "Kygo",
    "KygoMusic": "Kygo",
    "bausa": "BAUSA",
    "Bausa": "BAUSA",
    "bausashaus": "BAUSA",
    "aggu31": "Ski Aggu",
    "MrSuicideSheep": "MÖWE",
    "möwe": "MÖWE",
    "Mowe": "MÖWE",
    "MOWE": "MÖWE",
    "RobinSchulz": "Robin Schulz",
    "robin schulz": "Robin Schulz",
    "sido": "Sido",
    "SIDO": "Sido",
    "01099": "01099",
    "lea": "LEA",
    "Lea": "LEA",
    "LeA": "LEA",
    "badchieff": "Badchieff",
}

    # Standard-Metadaten
    METADATA_DEFAULTS = {
        "genre": None,
        "album": "Single", # Setze Album-Standard auf "Single"
        "album_artist": "Various Artists",
        "year": str(datetime.now().year), # Standard-Jahr auf aktuelles Jahr
        "track_number": "01", # Standard-Tracknummer
    }

    DEFAULT_ALBUM_NAME = "Singles"
    UNKNOWN_PLAYLIST = "Unbekannte Playlist"
    MAX_CONCURRENT_DOWNLOADS = 5
    DEBUG_MODE = False

    # METADATA_CONFIG (bleibt wie zuvor angepasst)
    METADATA_CONFIG = {
        "sources": {
            # ...
        },
        "fields": {
            # ...
            "album": {"required": False, "default": METADATA_DEFAULTS["album"]},
            "album_artist": {
                "required": False,
                "use_artist_if_missing": True,
                "default": METADATA_DEFAULTS["album_artist"],
            },
            "track_number": {
                "required": False,
                "default": METADATA_DEFAULTS["track_number"],
            },
            "album_type": {"required": False, "default": "single"},
            "is_single": {"required": False, "default": True},
        },
    }

    METADATA_CONFIG = {
        "sources": {
            "youtube": {"enabled": True, "priority": 3},
            "musicbrainz": {"enabled": MUSICBRAINZ_ENABLED, "priority": 1},
            "genius": {
                "enabled": bool(
                    GENIUS_CONFIG["fetch_lyrics"] or GENIUS_CONFIG["fetch_cover_art"]
                ),
                "priority": 2,
            },
            "lastfm": {"enabled": LASTFM_ENABLED, "priority": 4},
        },
        "fields": {
            "artist": {"required": True, "normalize": True},
            "title": {"required": True, "normalize": True},
            "album": {"required": False, "default": METADATA_DEFAULTS["album"]},
            "album_artist": {
                "required": False,
                "use_artist_if_missing": True,
                "default": METADATA_DEFAULTS["album_artist"],
            },
            "genre": {
                "required": False,
                "multiple": True,
                "default": METADATA_DEFAULTS["genre"],
            },
            "year": {
                "required": False,
                "format": "%Y",
                "default": METADATA_DEFAULTS["year"],
            },
            "track_number": {
                "required": False,
                "default": METADATA_DEFAULTS["track_number"],
            },
            "total_tracks": {"required": False},
            "disc_number": {"required": False},
            "total_discs": {"required": False},
            "composer": {"required": False},
            "lyrics": {"required": False},
            "album_type": {"required": False, "default": "single"},
            "is_single": {"required": False, "default": True},
        },
        "artist_rules": {
            r"\s*\(feat\..+?\)": "",
            r"\s*\(feat.\..+?\)": "",
            r"\s*&\s*": ", ",
            r"\s*vs\.?\s*": ", ",
            r"\s*x\.?\s*": ", ",
            r"\s*X\.?\s*": ", ",
            r"(?i)^makko.*": "makko",
            r"(?i)^Zartmann.*": "Zartmann",
            r"(?i)^01099.*": "01099",
            r"(?i)^Pashanim.*": "Pashanim",
            r"(?i)^Dante YN.*": "Dante YN",
            r"(?i)^Kygo.*": "Kygo",
            r"(?i)^MÖWE.*": "MÖWE",
            r"(?i)^Robin Schulz.*": "Robin Schulz",
            r"(?i)^2Pac.*": "2Pac",
            r"(?i)^Ski Aggu.*": "Ski Aggu",
            r"(?i)^Max Giesinger.*": "Max Giesinger",
        },
    }

    # YouTube-Kanal-Einstellungen
    YOUTUBE_CHANNELS = {
        "makko": "UCeL9e1tUEf1XFmWggnFVy_g",  # MakkoOfficial
        "zartmann": "UC4uR-YkZ0Lfk8aFnXvW0ciA",  # Zartizartmann
        "01099": "UC4Ibn2vjTqkQl34dUA8T0A",  # 01099official
        "badchieff": "UCr3gNc5M5UHNQJ9x2i1TzZw",  # Badchieff
    }
    YOUTUBE_CHECK_INTERVAL = 300  # in Sekunden (5 Minuten)

    @classmethod
    def init(cls):
        os.makedirs(cls.DOWNLOAD_DIR, exist_ok=True)
        os.makedirs(cls.PROCESSED_DIR, exist_ok=True)
        os.makedirs(cls.LIBRARY_DIR, exist_ok=True)
        os.makedirs(cls.LOG_DIR, exist_ok=True)
        os.makedirs(cls.ARCHIVE_DIR, exist_ok=True)
    
        for special_dir in cls.ORGANIZER_CONFIG["special_dirs"]:
            os.makedirs(cls.LIBRARY_DIR / special_dir, exist_ok=True)
    
        cls.genius = lyricsgenius.Genius(
            cls.GENIUS_TOKEN,
            verbose=cls.GENIUS_CONFIG["fetch_lyrics"],
            remove_section_headers=cls.GENIUS_CONFIG["remove_section_headers"],
            skip_non_songs=cls.GENIUS_CONFIG["skip_non_songs"],
            timeout=cls.GENIUS_CONFIG["timeout"],
            retries=cls.GENIUS_CONFIG["retry_attempts"],
        )
    
        musicbrainzngs.set_useragent(
            "YT-Music-Downloader", "1.0", "robinmarina070721@gmail.com"
        )        
    # Warnungen entfernen 
        logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    @classmethod
    def validate(cls):
        assert hasattr(cls, "GENIUS_CONFIG"), "Missing Genius configuration"


class ProductionConfig(Config):
    pass


import logging

class LogConfig:
    LEVEL = logging.DEBUG  # Nicht logging.INFO oder WARNING


class PerfConfig:
    MAX_IO_CONCURRENCY = 100  # Für SSDs/NVMe
    CACHE_SIZE_MB = 512  # Für Systeme mit >8GB RAM
    THUMBNAIL_CACHE = True  # Für häufige Thumbnail-Nutzung


Config.init()


