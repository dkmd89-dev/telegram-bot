# yt_music_bot/cookie_handler.py

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class CookieHandler:
    """Verwaltet Cookie-Dateien für YouTube-Downloads."""

    def __init__(
        self, cookie_path: Optional[str] = None, bot_directory: Optional[str] = None
    ):
        """Initialisiert den Cookie-Handler.

        Args:
            cookie_path: Optionaler Pfad zur Cookie-Datei.
            bot_directory: Optionaler Pfad zum Bot-Verzeichnis (nur verwendet, wenn cookie_path nicht gesetzt ist).
        """
        self.bot_directory = bot_directory or os.path.dirname(os.path.abspath(__file__))
        self.cookie_path = cookie_path or os.path.join(
            self.bot_directory, "cookies.txt"
        )

    def has_cookies(self) -> bool:
        """Überprüft, ob die Cookie-Datei existiert und gültig ist."""
        if not os.path.exists(self.cookie_path):
            return False
        if os.path.getsize(self.cookie_path) < 10:  # Mindestgröße
            return False
        return True

    def backup_cookies(self) -> Optional[str]:
        """Erstellt ein Backup der Cookie-Datei."""
        if not self.has_cookies():
            return None

        backup_dir = os.path.join(self.bot_directory, "backups")
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"cookies_{timestamp}.txt")

        try:
            shutil.copy2(self.cookie_path, backup_path)
            logger.info(f"Cookie-Backup erstellt: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Fehler beim Cookie-Backup: {str(e)}")
            return None

    def install_cookies(self, new_cookie_path: str) -> bool:
        """Installiert eine neue Cookie-Datei."""
        if not os.path.exists(new_cookie_path):
            logger.error(f"Cookie-Datei nicht gefunden: {new_cookie_path}")
            return False

        if self.has_cookies():
            self.backup_cookies()

        try:
            shutil.copy2(new_cookie_path, self.cookie_path)
            logger.info(f"Neue Cookie-Datei installiert von {new_cookie_path}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Installieren der Cookie-Datei: {str(e)}")
            return False

    def get_cookie_info(self) -> dict:
        """Gibt Informationen über die Cookie-Datei zurück."""
        if not self.has_cookies():
            return {"status": "missing", "message": "Keine Cookie-Datei gefunden"}

        try:
            stat = os.stat(self.cookie_path)
            modified = datetime.fromtimestamp(stat.st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            size = stat.st_size

            with open(self.cookie_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                domain_count = content.count(".youtube.com")

            return {
                "status": "valid",
                "path": self.cookie_path,
                "size": size,
                "modified": modified,
                "domains": domain_count,
                "message": f"Cookie-Datei gefunden ({size} Bytes, {domain_count} YouTube-Domains)",
            }
        except Exception as e:
            return {
                "status": "error",
                "path": self.cookie_path,
                "message": f"Fehler beim Lesen der Cookie-Datei: {str(e)}",
            }
