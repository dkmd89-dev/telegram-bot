# -*- coding: utf-8 -*-
from typing import Any, Dict, List, Union, Optional, Tuple

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    import requests
    HAS_HTTPX = False
    from logger import log_info
    log_info("httpx nicht verfügbar, verwende requests als Fallback", "command_handler")
import time
import subprocess
import requests
import io
from telegram.error import BadRequest
from urllib.parse import quote
from datetime import datetime, timedelta
import psutil
import re
import json
import os
import asyncio
import asyncio.subprocess
from pathlib import Path
from telegram import Update, Message, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    Application,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from telegram.helpers import escape_markdown
from api.navidrome_api import NavidromeAPI
from services.commands_services import COMMAND_CATEGORIES, COMMAND_DESCRIPTIONS
from handlers.button_handler import handle_button_click, handle_start, handle_help
from handlers.cover_handler import handle_fixcovers
from handlers.lyrics_handler import handle_fixlyrics
from handlers.fix_genres_handler import handle_fix_genres
from handlers.rescan_genres_handler import handle_rescan_genres
from handlers.check_artists_handler import handle_check_artists
from handlers.reprocess_handler import reprocess_library
from logger import log_info, log_error
from config import Config
from services.downloader import YoutubeDownloader
from handlers.message_handler import handle_message
from helfer.markdown_helfer import escape_md_v2
from klassen.artist_map import ARTIST_RULES, ARTIST_OVERRIDES
from emoji import EMOJI
from klassen.navidrome_stats import NavidromeStats
from klassen.stats_handler import StatsHandler
from klassen.download_handler import DownloadHandler
import logging

logger = logging.getLogger("command_handler")

def escape_md_v2(text: str) -> str:
    """Escapes MarkdownV2 special characters"""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)

async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt den Systemstatus an"""
    reply_target = update.callback_query.message if update.callback_query else update.message
    if not reply_target:
        log_error("No message context to reply to in handle_status", "command_handler")
        return

    msg = await reply_target.reply_text(
        f"{EMOJI['processing']} Prüfe Systemstatus..."
    )
    try:
        storage = psutil.disk_usage("/")
        used_gb = round(storage.used / (1024**3), 1)
        total_gb = round(storage.total / (1024**3), 1)
        storage_text = f"{used_gb}GB/{total_gb}GB genutzt ({storage.percent}%)"

        try:
            url = f"{Config.NAVIDROME_URL.rstrip('/')}/rest/ping.view"
            params = {
                "u": Config.NAVIDROME_USER,
                "p": quote(Config.NAVIDROME_PASS),
                "v": "1.16.0",
                "c": "yt_music_bot",
                "f": "json",
            }
        
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, params=params)
                data = response.json()
                status = data.get("subsonic-response", {}).get("status")
                navidrome_status = "Verbunden" if status == "ok" else "Nicht verbunden"
        except Exception as e:
            log_warning(f"Navidrome-Ping fehlgeschlagen: {e}", "handle_status")
            navidrome_status = "Nicht verbunden"

        status_lines = [
            f"{EMOJI['success']} *Systemstatus*",
            f"{EMOJI['running']} Bot: Online",
            f"{EMOJI['navidrome']} Navidrome: {navidrome_status}",
            f"{EMOJI['storage']} Speicher: {storage_text}",
        ]
        await msg.edit_text(
            escape_md_v2("\n".join(status_lines)), parse_mode="MarkdownV2"
        )
    except Exception as e:
        log_error(f"Fehler in handle_status: {str(e)}", "command_handler")
        await msg.edit_text(
            f"{EMOJI['error']} Status konnte nicht ermittelt werden",
            parse_mode="MarkdownV2",
        )

async def handle_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Erstellt ein System-Backup mit Fortschrittsanzeige in Telegram (max. alle 2 Sekunden)"""
    reply_target = update.callback_query.message if update.callback_query else update.message
    if not reply_target:
        log_error("No message context to reply to in handle_backup", "command_handler")
        return

    msg = await reply_target.reply_text(f"{EMOJI['processing']} Starte Backup-Prozess...")

    try:
        backup_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "backup.sh"
        )

        process = await asyncio.create_subprocess_shell(
            f"bash {backup_script}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        output_lines = []
        last_update_time = 0

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded_line = line.decode(errors="replace").strip()
            output_lines.append(decoded_line)

            now = time.time()
            if now - last_update_time > 2:
                last_update_time = now
                summary = "\n".join(output_lines[-5:])
                text = f"{EMOJI['processing']} Backup läuft...\n```{escape_md_v2(summary)}```"
                try:
                    await msg.edit_text(text, parse_mode="MarkdownV2")
                except Exception as e:
                    logger.error(f"[handle_backup] Fehler beim Telegram edit_text: {e}")

        await process.wait()

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            all_lines = stdout.decode(errors="replace").splitlines()
            summary = "\n".join(all_lines[-6:-1])
            text = f"{EMOJI['success']} *Backup erfolgreich*\n\n```{escape_md_v2(summary)}```"
            await msg.edit_text(text, parse_mode="MarkdownV2")
        else:
            error_msg = (stderr.decode(errors="replace") or stdout.decode(errors="replace"))[-400:]
            text = f"{EMOJI['error']} *Backup fehlgeschlagen*\n\n```{escape_md_v2(error_msg)}```"
            await msg.edit_text(text, parse_mode="MarkdownV2")
            log_error(f"Backup failed: {error_msg}", "command_handler")

    except Exception as e:
        error_text = escape_md_v2(str(e))
        await msg.edit_text(
            f"{EMOJI['error']} Fehler beim Backup: {error_text}",
            parse_mode="MarkdownV2",
        )
        log_error(f"Backup error: {str(e)}", "command_handler")

def register_command_handlers(application: Application):
    """Registriert alle Befehls-Handler mit korrekter Struktur"""        
    application.add_handler(CommandHandler("navidrome", lambda update, context: StatsHandler(update).handle_navidrome_stats(context)))
    application.add_handler(CommandHandler("scan", lambda update, context: StatsHandler(update).handle_scan_command(context)))
    application.add_handler(CommandHandler("genres", lambda update, context: StatsHandler(update).handle_genres(context)))
    application.add_handler(CommandHandler("artists", lambda update, context: StatsHandler(update).handle_artists(context)))
    application.add_handler(CommandHandler("indexes", lambda update, context: StatsHandler(update).handle_indexes(context)))
    application.add_handler(CommandHandler("albumlist", lambda update, context: StatsHandler(update).handle_albumlist(context)))
    application.add_handler(CommandHandler("topsongs", lambda update, context: StatsHandler(update).handle_top_songs(context)))
    application.add_handler(CommandHandler("topsongs7", lambda update, context: StatsHandler(update).handle_top_songs(context, period="week")))
    application.add_handler(CommandHandler("topartists", lambda update, context: StatsHandler(update).handle_top_artists(context)))
    application.add_handler(CommandHandler("monthreview", lambda update, context: StatsHandler(update).handle_month_review(context)))
    application.add_handler(CommandHandler("yearreview", lambda update, context: StatsHandler(update).handle_year_review(context)))
    application.add_handler(CommandHandler("playing", lambda update, context: StatsHandler(update).handle_playing(context)))
    application.add_handler(CommandHandler("lastplayed", lambda update, context: StatsHandler(update).handle_last_played(context)))

    application.add_handler(CommandHandler("fixcovers", handle_fixcovers))
    application.add_handler(CommandHandler("fixlyrics", handle_fixlyrics))
    application.add_handler(CommandHandler("fixgenres", handle_fix_genres))
    application.add_handler(CommandHandler("rescan_genres", handle_rescan_genres))
    application.add_handler(CommandHandler("check_artists", handle_check_artists))
    

    application.add_handler(CommandHandler("download", lambda update, context: DownloadHandler(update).handle_download(context)))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda update, context: DownloadHandler(update).handle_youtube_links(context)))

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("help", handle_help))
    application.add_handler(CommandHandler("status", handle_status))
    application.add_handler(CommandHandler("backup", handle_backup))
    application.add_handler(CommandHandler("reprocess_library", reprocess_library))
    application.add_handler(CallbackQueryHandler(handle_button_click))