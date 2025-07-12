import logging
from logging.handlers import RotatingFileHandler
from config import LogConfig, Config
import os
import traceback
from typing import Optional
import requests
import re

# Hauptlogger vorbereiten (nicht global aktivieren, da wir setup_logger nutzen!)
# logging.basicConfig(...) NICHT notwendig

class TelegramHandler(logging.Handler):
    """Custom Handler to send error and critical logs to Telegram."""
    MAX_MESSAGE_LENGTH = 4000  # Telegram-Hardlimit

    def __init__(self, bot_token: str, chat_id: str):
        super().__init__()
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.setLevel(logging.ERROR)
        logging.getLogger("yt_music_bot").debug(f"TelegramHandler initialisiert mit Token: {bot_token[:10]}... und Chat-ID: {chat_id}")

    def send_message(self, message: str):
        """Sendet eine Nachricht synchron an den Telegram-Chat (mit Markdown)."""
        message = re.sub(r'[^\x00-\x7F]+', '', message)  # Nicht-ASCII-Zeichen entfernen

        if len(message) > self.MAX_MESSAGE_LENGTH:
            message = message[:self.MAX_MESSAGE_LENGTH - 50] + "\n\n...(gekürzt)"

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": f"🚨 *Fehler aufgetreten:*\n```{message}```",
            "parse_mode": "Markdown",
        }

        try:
            logging.getLogger("yt_music_bot").debug(f"Versuche Telegram-Nachricht zu senden: {message[:200]}...")
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                logging.getLogger("yt_music_bot").error(f"Telegram-Sendefehler: {response.status_code} - {response.text}")
            else:
                logging.getLogger("yt_music_bot").debug("Telegram-Nachricht erfolgreich gesendet.")
        except Exception as e:
            logging.getLogger("yt_music_bot").error(f"Fehler beim Senden der Telegram-Nachricht: {str(e)}")

    def emit(self, record: logging.LogRecord):
        """Verarbeitet einen Log-Eintrag und sendet ihn an Telegram."""
        try:
            message = self.format(record)
            self.send_message(message)
        except Exception as e:
            logging.getLogger("yt_music_bot").error(f"Fehler im TelegramHandler emit: {str(e)}")
            self.handleError(record)


def setup_logger(name: str) -> logging.Logger:
    """Konfiguriert den Logger mit Rotation, Konsole und Telegram."""
    logger = logging.getLogger(name)
    logger.setLevel(LogConfig.LEVEL)

    # Log-Verzeichnis sicherstellen
    os.makedirs(Config.LOG_DIR, exist_ok=True)

    # === FILE HANDLER (INFO+) ===
    file_handler = RotatingFileHandler(
        filename=os.path.join(Config.LOG_DIR, f"{name}.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    
    # === DEBUG HANDLER (DEBUG) ===
    debug_handler = RotatingFileHandler(
        filename=os.path.join(Config.LOG_DIR, f"{name}_debug.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    debug_handler.setLevel(logging.DEBUG)
    
    # === CONSOLE HANDLER (LEVEL aus LogConfig) ===
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LogConfig.LEVEL)
    
    # === TELEGRAM HANDLER ===
    telegram_handler = TelegramHandler(Config.BOT_TOKEN, Config.ADMIN_CHAT_ID)
    telegram_handler.setLevel(logging.ERROR)
    
    # === FORMATTER ===
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    debug_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    telegram_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s\n%(message)s'))
    
    # === HANDLER REGISTRIEREN ===
    logger.addHandler(file_handler)
    logger.addHandler(debug_handler)
    logger.addHandler(console_handler)
    logger.addHandler(telegram_handler)

    # Fremdmodule runterregeln (kein DEBUG-Spam!)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logger


# Hauptlogger initialisieren
logger = setup_logger("yt_music_bot")


# Hilfsfunktionen für den Import
def log_debug(message: str, context: str = None):
    if context:
        message = f"[{context}] {message}"
    logger.debug(message)


def log_info(message: str, context: str = None):
    if context:
        message = f"[{context}] {message}"
    logger.info(message)


def log_warning(message: str, context: str = None):
    if context:
        message = f"[{context}] {message}"
    logger.warning(message)


def log_error(error: Exception, context: str = None, exc_info: bool = True):
    """Fehler mit vollständigem Stacktrace loggen (inkl. Telegram)."""
    error_msg = f"{type(error).__name__}: {str(error)}"
    if context:
        error_msg = f"[{context}] {error_msg}"
    logger.error(error_msg, exc_info=error)


def log_critical(message: str, context: str = None):
    if context:
        message = f"[{context}] {message}"
    logger.critical(message)


# Testfunktionen
def test_telegram_notification():
    """Testet den TelegramHandler mit absichtlich ausgelöstem Fehler."""
    logger.debug("Teste Telegram-Benachrichtigung...")
    try:
        raise Exception("Test")
    except Exception as e:
        log_error(e, context="MinimalTest")


def test_telegram_api():
    """Testet den Telegram-API-Aufruf direkt."""
    logger.debug("Teste direkte Telegram-API...")
    url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": Config.ADMIN_CHAT_ID,
        "text": "✅ Direkter Test der Telegram-API war erfolgreich.",
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Fehler beim Telegram-API-Test: {response.text}")
        else:
            logger.debug("Direkter Telegram-API-Test erfolgreich.")
    except Exception as e:
        logger.error(f"Telegram-API-Testfehler: {str(e)}")


# Optional zum Testen
if __name__ == "__main__":
    test_telegram_notification()
    # test_telegram_api()