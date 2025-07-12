from telegram import Update
from telegram.ext import ContextTypes

async def find_duplicates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Duplikate werden noch nicht überprüft – Funktion in Arbeit.")
