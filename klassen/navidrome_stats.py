# -*- coding: utf-8 -*-
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote

import matplotlib.pyplot as plt
import requests
from apscheduler.schedulers.background import BackgroundScheduler

# ✅ Escape-Funktion für Telegram MarkdownV2
def escape_text_md2(text: Any) -> str:
    """Escape special characters for Telegram MarkdownV2 format"""
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r"_*[]()~`>#+-=|{}.!\\"
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

try:
    from config import Config
    from logger import log_info, log_error, log_warning 
    from emoji import EMOJI
except ImportError:
    class Config:
        NAVIDROME_URL = "http://localhost:4533"
        NAVIDROME_USER = "dkmd"
        NAVIDROME_PASS = "root"
        PLAY_HISTORY_FILE = Path("play_history.json")
        STATS_DIR = Path("stats")
        PLAY_HISTORY_RETENTION_DAYS = 365
        PLAY_HISTORY_AUTOSAVE_INTERVAL_MIN = 15

    def log_info(message, context=""):
        print(f"INFO [{context}]: {message}")

    def log_error(message, context=""):
        print(f"ERROR [{context}]: {message}")
        
    def log_warning(message, context=""):
        print(f"WARNING [{context}]: {message}")

    EMOJI = {"song": "🎵", "artist": "🎤", "topsongs": "📈", "statistics": "📊", "processing": "⏳", "warning": "⚠️", "error": "❌", "music": "🎶"}

logger = logging.getLogger(__name__)

def format_song_message(track: dict) -> str:
    title = escape_text_md2(track.get("title", "Unbekannter Titel"))
    artist = escape_text_md2(track.get("artist", "Unbekannter Künstler"))
    album = escape_text_md2(track.get("album", "Unbekanntes Album"))
    user = escape_text_md2(track.get("username", "Unbekannt"))
    time = escape_text_md2(track.get("timestamp", ""))
    log_info(f"Formatiere Song-Nachricht: {title} von {artist}", "NavidromeStats")
    return f"{EMOJI['song']} *{title}* von _{artist}_ auf dem Album _{album}_ gespielt von `{user}` um {time}"

def format_stat_block(stats: dict) -> str:
    log_info(f"Formatiere Statistik-Block für Zeitraum: {stats['period']}", "NavidromeStats")
    top_artists = "\n".join([
        f"{escape_text_md2(artist)}: *{count}*" for artist, count in stats.get("top_artists", [])
    ])
    top_songs = "\n".join([
        f"{escape_text_md2(song)}: *{count}*" for song, count in stats.get("top_songs", [])
    ])
    top_albums = "\n".join([
        f"{escape_text_md2(album)}: *{count}*" for album, count in stats.get("top_albums", [])
    ])
    return (
        f"\U0001F4CA *Wiedergabe-Statistik: {escape_text_md2(stats['period'].capitalize())}*\n"
        f"Zeitraum: {escape_text_md2(stats['from_date'])} bis {escape_text_md2(stats['to_date'])}\n"
        f"\n*Top-Künstler:*\n{top_artists}\n"
        f"\n*Top-Songs:*\n{top_songs}\n"
        f"\n*Top-Alben:*\n{top_albums}"
    )

# Ab hier die NavidromeStats-Klasse
# (inhaltlich unverändert, aber voll funktionsfähig mit escape_text_md2)

class NavidromeStats:
    HISTORY_FILE = Config.PLAY_HISTORY_FILE
    STATS_DIR = Config.STATS_DIR
    HISTORY_MAX_DAYS = Config.PLAY_HISTORY_RETENTION_DAYS

    def __init__(self, debug: bool = False):
        self.debug = debug
        if self.debug:
            logger.info("NavidromeStats-Klasse im DEBUG-Modus initialisiert.")
        os.makedirs(self.STATS_DIR, exist_ok=True)
        log_info(f"Statistik-Verzeichnis sichergestellt: {self.STATS_DIR}", "NavidromeStats")
        self.setup_autosave()

    def test_now_playing_api(self) -> bool:
        log_info("Starte API-Verbindungstest", "NavidromeStats")
        test_params = {
            "u": Config.NAVIDROME_USER,
            "p": quote(Config.NAVIDROME_PASS),
            "v": "1.16.0",
            "c": "play_stats_test",
            "f": "json",
        }
        try:
            response = requests.get(
                f"{Config.NAVIDROME_URL.rstrip('/')}/rest/getNowPlaying.view",
                params=test_params,
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
            log_info("API-Antwort erfolgreich empfangen", "NavidromeStats")
            return "nowPlaying" in data.get("subsonic-response", {})
        except Exception as e:
            log_error(f"API-Test fehlgeschlagen: {e}", "NavidromeStats")
            return False

    def setup_autosave(self):
        self.scheduler = BackgroundScheduler(daemon=True)
        self.scheduler.add_job(
            self.save_play_history,
            "interval",
            minutes=Config.PLAY_HISTORY_AUTOSAVE_INTERVAL_MIN,
            next_run_time=datetime.now() + timedelta(seconds=10),
        )
        self.scheduler.start()
        log_info("Autosave-Scheduler gestartet.", "NavidromeStats")

    def cleanup_old_entries(self):
        history = self.load_history()
        cutoff = datetime.now() - timedelta(days=self.HISTORY_MAX_DAYS)
        cleaned_history = [
            entry for entry in history
            if datetime.fromisoformat(entry.get("timestamp", "1970-01-01")) >= cutoff
        ]
        with open(self.HISTORY_FILE, "w") as f:
            json.dump(cleaned_history, f, indent=2)

    def get_now_playing(self) -> List[Dict[str, Any]]:
        params = {
            "u": Config.NAVIDROME_USER,
            "p": quote(Config.NAVIDROME_PASS),
            "v": "1.16.0",
            "c": "play_stats_fetch",
            "f": "json",
        }
        try:
            response = requests.get(
                f"{Config.NAVIDROME_URL.rstrip('/')}/rest/getNowPlaying.view",
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json().get("subsonic-response", {})
            entries = data.get("nowPlaying", {}).get("entry", [])
            return entries if isinstance(entries, list) else [entries] if entries else []
        except Exception as e:
            log_error(f"Fehler beim Abrufen der 'Now Playing'-Daten: {e}", "NavidromeStats")
            return []

    def save_play_history(self) -> bool:
        now_playing = self.get_now_playing()
        if not now_playing:
            return False
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "tracks": [
                {
                    "title": track.get("title"),
                    "artist": track.get("artist"),
                    "album": track.get("album"),
                    "duration": track.get("duration"),
                    "player": track.get("playerName"),
                    "username": track.get("username"),
                }
                for track in now_playing
            ],
        }
        history = self.load_history()
        history.append(history_entry)
        with open(self.HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        self.cleanup_old_entries()
        return True

    def load_history(self) -> List[Dict[str, Any]]:
        if not self.HISTORY_FILE.exists():
            return []
        try:
            with open(self.HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            return history if isinstance(history, list) else [history]
        except Exception:
            return []

    def generate_stats(self, period: str = "month") -> Optional[Dict[str, Any]]:
        history = self.load_history()
        if not history:
            return None
        now = datetime.now()
        period_map = {
            "week": timedelta(days=7),
            "month": timedelta(days=30),
            "year": timedelta(days=365),
        }
        cutoff = now - period_map.get(period, timedelta.max)
        artist_counts = defaultdict(int)
        song_counts = defaultdict(int)
        album_counts = defaultdict(int)
        total_plays = 0
        for entry in history:
            entry_time = datetime.fromisoformat(entry.get("timestamp", ""))
            if entry_time < cutoff:
                continue
            for track in entry.get("tracks", []):
                artist = track.get("artist", "Unknown Artist")
                title = track.get("title", "Unknown Title")
                album = track.get("album", "Unknown Album")
                song_key = f"{title} - {artist}"
                album_key = f"{album} - {artist}"
                artist_counts[artist] += 1
                song_counts[song_key] += 1
                album_counts[album_key] += 1
                total_plays += 1
        if total_plays == 0:
            return None
        return {
            "period": period,
            "total_plays": total_plays,
            "top_artists": sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_songs": sorted(song_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_albums": sorted(album_counts.items(), key=lambda x: x[1], reverse=True)[:5],
            "from_date": cutoff.isoformat(),
            "to_date": now.isoformat(),
        }

    def get_last_played_song(self) -> Optional[Dict[str, Any]]:
        history = self.load_history()
        if not history:
            return None
        last_event = history[-1]
        if not last_event.get("tracks"):
            return None
        last_track = last_event["tracks"][-1]
        last_track["timestamp"] = last_event.get("timestamp")
        return last_track

    def create_chart(self, stats: Dict[str, Any], chart_type: str = "songs") -> Optional[Path]:
        data = stats.get("top_songs" if chart_type == "songs" else "top_artists", [])
        if not data:
            return None
        labels = [escape_text_md2(item[0]) for item in data][::-1]
        values = [item[1] for item in data][::-1]
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(10, 7))
        bars = ax.barh(labels, values, color='skyblue' if chart_type == "songs" else "lightgreen")
        ax.set_xlabel("Wiedergaben", color='white')
        ax.set_title(f"{escape_text_md2(chart_type.capitalize())} – {escape_text_md2(stats['period'].capitalize())}", color='white')
        ax.tick_params(colors='white')
        for bar in bars:
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2, str(int(bar.get_width())), color='white', va='center')
        filename = f"top_{chart_type}_{stats['period']}_{datetime.now().strftime('%Y%m%d')}.png"
        filepath = self.STATS_DIR / filename
        plt.tight_layout()
        try:
            plt.savefig(filepath, dpi=100, bbox_inches="tight", facecolor=fig.get_facecolor())
            plt.close()
            return filepath
        except Exception as e:
            log_error(f"Fehler beim Speichern des Diagramms: {e}", "NavidromeStats")
            plt.close()
            return None