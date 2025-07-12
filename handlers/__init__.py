from telegram.ext import CommandHandler, MessageHandler, filters
from .status_handler import status
from .message_handler import handle_message

def get_command_handlers():
    """Returns all command handlers"""
    return [
        CommandHandler("start", handle_start),
        CommandHandler("status", status),
        # Fügen Sie hier weitere CommandHandler hinzu
    ]

def get_message_handlers():
    """Returns all message handlers"""
    return [
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
        # Fügen Sie hier weitere MessageHandler hinzu
    ]

def register_handlers(app):
    """Registers all handlers for the Telegram bot application"""
    # Register command handlers
    for handler in get_command_handlers():
        app.add_handler(handler)
    
    # Register message handlers
    for handler in get_message_handlers():
        app.add_handler(handler)