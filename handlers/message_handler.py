# -*- coding: utf-8 -*-
import re
from typing import Any, Dict, List, Union, Optional, Tuple
from telegram import Update, Message
from telegram.ext import ContextTypes
from pathlib import Path

from services.downloader import YoutubeDownloader
from logger import log_info, log_error, log_warning, log_debug

YOUTUBE_REGEX = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/[^\s]+"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main entry point for message handling"""
    try:
        user_id = update.effective_user.id
        message_text = update.message.text.strip()

        log_debug(f"Message received from user {user_id}", context="message_handler")
        log_debug(f"Message content: {message_text}", context="message_handler")

        if not (url := extract_youtube_url(message_text)):
            log_warning("Invalid input received - not a YouTube URL", 
                       context="message_handler")
            await handle_invalid_input(update, user_id)
            return

        await process_audio_download(url, update, user_id)

    except Exception as e:
        log_error(e, "Unexpected error in message handler", context="message_handler")
        await send_error_message(update)

async def process_audio_download(url: str, update: Update, user_id: int) -> None:
    """Process the audio download workflow with enhanced status messages."""
    log_info(f"Processing audio download for user {user_id}", context="message_handler")

    status_msg = await update.message.reply_text("Starting download...")

    downloader = YoutubeDownloader(update)
    try:
        processed_result = await downloader.download_audio(url)
        if processed_result:
            log_info(f"Download successful, cover art processed: {processed_result.get('file_path')}")
            await handle_download_success(update, status_msg, processed_result)
        else:
            await handle_download_failure(update, status_msg, "Download returned no result.")
    except Exception as e:
        error_message = f"❌ Unexpected error: {str(e)}"
        log_error(f"Unexpected error in process_audio_download: {str(e)}", context="message_handler", exc_info=True)
        await handle_download_failure(update, status_msg, error_message)

def process_download_result(result: Union[Dict[str, Any], str, None]) -> Dict[str, Any]:
    """Process download result and return standardized dictionary"""
    response = {
        "success": False,
        "error": None,
        "file_path": None,
        "title": "Unbekannter Titel",
        "filename": "unbekannte_datei",
    }

    if isinstance(result, dict):
        if result.get("success"):
            response.update({
                "success": True,
                "file_path": result.get("file_path"),
                "title": result.get("title", response["title"]),
                "filename": (Path(result["file_path"]).name 
                            if "file_path" in result 
                            else response["filename"]),
            })
        else:
            response["error"] = result.get("error", "Download fehlgeschlagen (unbekannter Fehler)")
    elif isinstance(result, str):
        response["error"] = result
    elif result is None:
        response["error"] = "Kein Ergebnis vom Downloader erhalten"
    else:
        response["error"] = f"Unbekanntes Ergebnisformat: {type(result)}"

    return response

async def handle_download_success(update: Update, status_msg: Message, result: Union[str, List[str]]):
    # Diese Funktion muss in message_handler.py oder einer helper-Datei definiert sein
    # um von process_audio_download aufgerufen zu werden.
    # ... Ihre Implementierung hier ...
    pass # Platzhalter

async def handle_download_failure(update: Update, status_msg: Message, error_msg: str):
    # Diese Funktion muss in message_handler.py oder einer helper-Datei definiert sein
    # um von process_audio_download aufgerufen zu werden.
    # Sie sollte KEINE Methoden auf dem Downloader-Objekt aufrufen.
    log_error(f"Download fehlgeschlagen: {error_msg}", "message_handler")

    try:
        await status_msg.edit_text(
            f"❌ *Download fehlgeschlagen*\n\n"
            f"Fehler: `{error_msg}`\n\n"
            f"Bitte versuche es später erneut oder mit einem anderen Link.",
            parse_mode="Markdown"
        )
    except Exception as e:
        log_error(f"Fehler beim Senden der Download-Fehlermeldung: {str(e)}", "message_handler")

def extract_youtube_url(text: str) -> Optional[str]:
    """Extract and validate YouTube URL from text"""
    if match := re.search(YOUTUBE_REGEX, text):
        return match.group(0)
    return None

async def handle_invalid_input(update: Update, user_id: int) -> None:
    """Handle non-YouTube input with friendly guidance"""
    log_warning(f"Invalid input from user {user_id}", context="input_validation")
    await update.message.reply_text(
        f"{get_emoji('warning')} *Ungültige Eingabe*\n\n"
        "Bitte sende einen gültigen YouTube-Link!\n"
        "Beispiel: `https://youtu.be/dQw4w9WgXcQ`",
        parse_mode="Markdown",
    )

async def send_error_message(update: Update) -> None:
    """Send generic error response with support info"""
    await update.message.reply_text(
        f"{get_emoji('error')} *Unerwarteter Fehler*\n\n"
        "Es ist ein unerwarteter Fehler aufgetreten. "
        "Bitte versuche es später noch einmal.\n\n"
        "Falls das Problem bestehen bleibt, kontaktiere den Support.",
        parse_mode="Markdown",
    )