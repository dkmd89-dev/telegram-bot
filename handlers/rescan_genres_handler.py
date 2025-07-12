# handlers/rescan_genres_handler.py
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
import asyncio

# Importiere die Hauptfunktion des Rescan-Genres-Befehls
from helfer.rescan_genres import rescan_genres_command # Dies ist jetzt die umbenannte Funktion

# Hinweis: Der Logger für rescan_genres_command wird direkt in rescan_genres.py eingerichtet.
# Hier im Handler brauchen wir keinen separaten Logger, es sei denn, der Handler
# selbst hat zusätzliche Logik außerhalb des Aufrufs von rescan_genres_command.

async def handle_rescan_genres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler für /rescan_genres – Startet den Genre-Rescan über Telegram"""
    
    # Die rescan_genres_command Funktion sendet bereits ihre eigene Anfangsnachricht
    # und die Abschlussnachricht. Daher rufen wir sie einfach auf.
    await rescan_genres_command(update, context)


# Dieser Handler müsste dann in Ihrem Haupt-Bot-Code registriert werden
# from telegram.ext import CommandHandler
# application.add_handler(CommandHandler("rescan_genres", handle_rescan_genres))