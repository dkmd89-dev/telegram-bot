#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import logging
import os
from pathlib import Path
from telegram.helpers import escape_markdown
from telegram.ext import Application
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from config import Config
from command_handler import register_command_handlers
from helfer.markdown_helfer import escape_md_v2
from handlers.message_handler import handle_message
from html import escape as html_escape

# Logging-Verzeichnis erstellen
os.makedirs(Config.LOG_DIR, exist_ok=True)
log_path = Config.LOG_DIR / "bot.log"

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_path, encoding="utf-8", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

# 🔇 APScheduler-Logs auf WARNING setzen → keine Info-Meldungen in Konsole
logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def send_status(message: str, is_error: bool = False, include_start_button: bool = False):
    """Sendet Statusmeldungen an den Admin-Chat und loggt sie"""
    try:
        application = Application.builder().token(Config.BOT_TOKEN).build()
        await application.initialize()

        escaped_message_content = html_escape(message)
        status_msg_html = f"<b>🤖 Status:\n{escaped_message_content}</b>"

        reply_markup = None
        if include_start_button:
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 /start", callback_data="/start")]
            ])

        await application.bot.send_message(
            chat_id=Config.ADMIN_CHAT_ID,
            text=status_msg_html,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

        if is_error:
            logger.critical(message)
        else:
            logger.info(message)

        await application.shutdown()

    except Exception as e:
        logger.error(f"Statusmeldung fehlgeschlagen: {escape_md_v2(str(e))}")


async def run_bot():
    from telegram.ext import MessageHandler, filters

    application = None

    try:
        logger.info("=" * 50)
        logger.info(f"🚀 Bot wird gestartet (Version: {Config.VERSION})")

        # Initialstatus an Admin
        await send_status(
            "⚡ Das ist der Musik Bot von xxX chiLL mal. "
            "Um in die Menüführung zu gelangen drück auf /start und schon kan es losgehen. "
            "Habt viel Spaß damit"
        )

        # Bot-Instanz erstellen
        application = Application.builder().token(Config.BOT_TOKEN).build()

        # Initialisieren
        await application.initialize()

        # Commands registrieren
        register_command_handlers(application)

        # Handler für normale Nachrichten
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )

        # Bot starten
        await application.start()
        logger.info("✅ Bot-Services initialisiert")

        await send_status(
            f"✅ Bot erfolgreich gestartet\nVersion: {Config.VERSION}",
            include_start_button=True
        )

        await application.updater.start_polling()
        logger.info("🔄 Polling gestartet - Bot ist online")

        # Blockieren, bis manuell gestoppt wird
        await asyncio.get_event_loop().create_future()

    except Exception as e:
        error_msg = f"KRITISCHER FEHLER: {escape_md_v2(str(e))}"
        logger.critical(error_msg, exc_info=True)
        await send_status(f"🚨 {error_msg}", is_error=True)

    finally:
        if application:
            logger.info("🛑 Bot wird heruntergefahren...")
            await send_status("🛑 Bot wird heruntergefahren")

            if getattr(application, "running", False):
                await application.stop()

            await application.shutdown()

        logger.info("=" * 50 + "\n")


def main():
    try:
        logger.info(f"🎧 Musikbot initialisiert - Logfile: {log_path}")
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.warning("⚠️ Manuell gestoppt (KeyboardInterrupt)")
        asyncio.run(send_status("⏸️ Manuell gestoppt"))
    except Exception as e:
        error_msg = f"FATALER FEHLER: {escape_md_v2(str(e))}"
        logger.critical(error_msg, exc_info=True)
        asyncio.run(send_status(f"💥 {error_msg}", is_error=True))


if __name__ == "__main__":
    main()