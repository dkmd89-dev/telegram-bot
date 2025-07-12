# handlers/status_handler.py
from telegram import Update
from telegram.ext import ContextTypes
from services.status_service import get_status
from logger import logger

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler für /status Befehl
    Zeigt den aktuellen Bot-Status an
    """
    try:
        # Statusdaten asynchron abrufen
        status_data = await get_status()
        
        # Formatierte Ausgabe erstellen
        status_message = (
            "🤖 Bot Status Report:\n"
            "──────────────────\n"
            f"👥 Active users: {status_data['active_users']}\n"
            f"⏱ Uptime: {status_data['uptime']}\n"
            "──────────────────\n"
            "✅ All systems operational"
        )
        
        # Antwort senden
        await update.message.reply_text(status_message)
        logger.info(f"Status angezeigt für User {update.effective_user.id}")
        
    except Exception as e:
        error_msg = "❌ Could not retrieve status data"
        await update.message.reply_text(error_msg)
        logger.error(f"Status error for {update.effective_user.id}: {e}")