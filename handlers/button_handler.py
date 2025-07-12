# handlers/button_handler.py

import logging
from typing import List, Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from emoji import EMOJI
from helfer.markdown_helfer import escape_md_v2 
from services.commands_services import COMMAND_CATEGORIES, COMMAND_DESCRIPTIONS
from api.navidrome_api import NavidromeAPI
from handlers.cover_handler import handle_fixcovers
from handlers.lyrics_handler import handle_fixlyrics  # New import
from handlers.fix_genres_handler import handle_fix_genres
from handlers.rescan_genres_handler import handle_rescan_genres
from klassen.navidrome_stats import NavidromeStats
from klassen.stats_handler import StatsHandler
from klassen.download_handler import DownloadHandler
from config import Config

logger = logging.getLogger("button_handler")

# --- Hilfsfunktionen ---

def truncate_callback_data(data: str, max_bytes: int = 60) -> str:
    """Truncates callback data to ensure it stays under Telegram's 64-byte limit."""
    encoded = data.encode('utf-8')
    if len(encoded) > max_bytes:
        logger.warning(f"Callback data too long: {data} ({len(encoded)} bytes), truncating...")
        while len(encoded) > max_bytes and len(data) > 0:
            data = data[:-1]
            encoded = data.encode('utf-8')
    return data

def generate_main_category_buttons() -> tuple[str, InlineKeyboardMarkup]:
    message = f"{EMOJI['robot']} <b>Hallo! Ich bin dein Navidrome Bot.</b>\n\n" \
              f"Wähle eine Kategorie, um mehr über die Befehle zu erfahren:"
    buttons = []
    for category_name in COMMAND_CATEGORIES.keys():
        callback_data = truncate_callback_data(f"category_{category_name}")
        buttons.append([InlineKeyboardButton(category_name, callback_data=callback_data)])
        logger.debug(f"Generated category button: {category_name} -> {callback_data}")
    reply_markup = InlineKeyboardMarkup(buttons)
    return message, reply_markup

def generate_subcategory_buttons(main_category_name: str, subcategories: Dict[str, List[str]]) -> tuple[str, InlineKeyboardMarkup]:
    message = f"<b>{EMOJI['info']} Unterkategorien in {main_category_name}:</b>\n\n" \
              f"Wähle eine Unterkategorie:"
    buttons = []
    for subcategory_name in subcategories.keys():
        callback_data = truncate_callback_data(f"subcategory_{main_category_name}_{subcategory_name}")
        buttons.append([InlineKeyboardButton(subcategory_name, callback_data=callback_data)])
        logger.debug(f"Generated subcategory button: {subcategory_name} -> {callback_data}")
    buttons.append([InlineKeyboardButton(f"{EMOJI['help']} Zurück zu Kategorien", callback_data="show_categories")])
    reply_markup = InlineKeyboardMarkup(buttons)
    return message, reply_markup

def generate_command_list(commands: List[str], parent_category_name: Optional[str] = None) -> tuple[str, InlineKeyboardMarkup]:
    message = f"<b>{EMOJI['info']} Verfügbare Befehle:</b>\n\n"
    command_buttons = []
    for cmd in commands:
        description_full = COMMAND_DESCRIPTIONS.get(cmd, f"Keine Beschreibung für /{cmd}")
        button_text_short = description_full.split(' ')[0][:10]  # Limit button text to avoid payload issues
        message += f"• <code>/{cmd}</code>: {description_full}\n"
        callback_data = truncate_callback_data(f"execute_cmd_{cmd}")
        if cmd == "download":
            command_buttons.append(InlineKeyboardButton(f"{EMOJI['info']} /download", callback_data="info_download_cmd"))
        elif cmd == "albumlist":
            command_buttons.append(InlineKeyboardButton(f"{EMOJI['album']} /albumlist", callback_data=callback_data))
        else:
            button_text = f"/{cmd}"  # Simplified button text
            command_buttons.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        logger.debug(f"Generated command button: {cmd} -> {callback_data}")
    rows = [command_buttons[i:i + 2] for i in range(0, len(command_buttons), 2)]
    back_button_text = f"{EMOJI['help']} Zurück"
    back_callback_data = "show_categories"
    if parent_category_name:
        back_button_text = f"{EMOJI['help']} Zurück zu {parent_category_name}"
        back_callback_data = truncate_callback_data(f"show_category_{parent_category_name}")
    rows.append([InlineKeyboardButton(back_button_text, callback_data=back_callback_data)])
    reply_markup = InlineKeyboardMarkup(rows)
    return message, reply_markup

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    user_id = query.from_user.id
    logger.info(f"🟦 Button clicked by user {user_id} with data: {callback_data}")

    command_update = Update(
        update_id=update.update_id,
        callback_query=query,
        message=query.message,
    )

    try:
        if callback_data.startswith("page_"):
            logger.debug(f"📄 Pagination callback received: {callback_data}")
            try:
                _, command, page_str = callback_data.split("_", 2)
                page = int(page_str)
                context.user_data[f"{command}_page"] = page
                logger.debug(f"📄 User {user_id} switching to page {page} of {command}")

                stats_handler = StatsHandler(command_update)
                if command == "genres":
                    logger.debug("➡️ Calling handle_genres from pagination")
                    await stats_handler.handle_genres(context)
                elif command == "artists":
                    logger.debug("➡️ Calling handle_artists from pagination")
                    await stats_handler.handle_artists(context)
                elif command == "indexes":
                    logger.debug("➡️ Calling handle_indexes from pagination")
                    await stats_handler.handle_indexes(context)
                else:
                    logger.warning(f"⚠️ Unknown pagination command: {command}")
                    await query.edit_message_text(f"{EMOJI['error']} Invalid pagination command: {command}")
            except Exception as e:
                logger.error(f"❌ Pagination parsing failed: {e}", exc_info=True)
                await query.edit_message_text(f"{EMOJI['error']} Invalid pagination format.")

        elif callback_data.startswith("category_"):
            category_name = callback_data.replace("category_", "")
            logger.debug(f"📁 Category selected: {category_name}")
            category_content = COMMAND_CATEGORIES.get(category_name)
            if category_content:
                if isinstance(category_content, dict):
                    message, reply_markup = generate_subcategory_buttons(category_name, category_content)
                    await query.edit_message_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
                else:
                    message, reply_markup = generate_command_list(category_content)
                    await query.edit_message_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            else:
                logger.warning(f"❓ Unknown category: {category_name}")
                await query.edit_message_text(f"{EMOJI['error']} Unknown category: {category_name}")

        elif callback_data.startswith("subcategory_"):
            parts = callback_data.split('_', 2)
            if len(parts) < 3:
                await query.edit_message_text(f"{EMOJI['error']} Invalid subcategory request.")
                return
            main_category_name, subcategory_name = parts[1], parts[2]
            logger.debug(f"📂 Subcategory selected: {main_category_name}/{subcategory_name}")
            commands = COMMAND_CATEGORIES.get(main_category_name, {}).get(subcategory_name)
            if commands:
                message, reply_markup = generate_command_list(commands, parent_category_name=main_category_name)
                await query.edit_message_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            else:
                logger.warning(f"❓ Unknown subcategory: {subcategory_name}")
                await query.edit_message_text(f"{EMOJI['error']} Unknown subcategory: {subcategory_name}")

        elif callback_data.startswith("execute_cmd_"):
            command = callback_data.replace("execute_cmd_", "")
            logger.info(f"▶️ Executing command from button: /{command} for user {user_id}")

            # Reset pagination
            for key in ["genres_page", "artists_page", "indexes_page"]:
                context.user_data[key] = 1

            stats_handler = StatsHandler(command_update)

            try:
                if command == "navidrome":
                    await stats_handler.handle_navidrome_stats(context)
                elif command == "scan":
                    await stats_handler.handle_scan_command(context)
                elif command == "artists":
                    logger.debug("➡️ Calling handle_artists from execute_cmd")
                    await stats_handler.handle_artists(context)
                elif command == "indexes":
                    await stats_handler.handle_indexes(context)
                elif command == "genres":
                    await stats_handler.handle_genres(context)
                elif command == "albumlist":
                    await stats_handler.handle_albumlist(context)
                elif command == "topsongs":
                    await stats_handler.handle_top_songs(context)
                elif command == "topsongs7":
                    await stats_handler.handle_top_songs(context, period="week")
                elif command == "topartists":
                    await stats_handler.handle_top_artists(context)
                elif command == "monthreview":
                    await stats_handler.handle_month_review(context)
                elif command == "yearreview":
                    await stats_handler.handle_year_review(context)
                elif command == "playing":
                    await stats_handler.handle_playing(context)
                elif command == "lastplayed":
                    await stats_handler.handle_last_played(context)
                elif command == "fixcovers":
                    await handle_fixcovers(command_update, context)
                elif command == "fixlyrics":  # New command handler
                    await handle_fixlyrics(command_update, context)
                elif command == "fixgenres":
                    await handle_fix_genres(command_update, context)
                elif command == "rescan_genres":
                    await handle_rescan_genres(command_update, context)
                elif command == "backup":
                    from command_handler import handle_backup
                    await handle_backup(command_update, context)
                elif command == "status":
                    from command_handler import handle_status
                    await handle_status(command_update, context)
                elif command == "help":
                    await handle_start(command_update, context)
                else:
                    logger.warning(f"❓ Unhandled command: /{command}")
                    await query.message.reply_text(f"{EMOJI['warning']} Command `/{command}` not implemented for buttons.")
            except Exception as e:
                logger.error(f"❌ Fehler bei der Ausführung von /{command}: {e}", exc_info=True)
                await query.edit_message_text(f"{EMOJI['error']} Fehler bei der Ausführung von /{command}")

        elif callback_data.startswith("albumlist_"):
            type_param = callback_data.replace("albumlist_", "")
            logger.debug(f"🎧 Albumlist param: {type_param}")
            await StatsHandler(command_update).handle_albumlist_criteria(context, type_param)

        elif callback_data in ["info_download_cmd"]:
            await query.message.reply_text(f"{EMOJI['info']} Für Downloads bitte `/download [URL]` verwenden.")

        elif callback_data in ["show_categories", "/start"]:
            await handle_start(command_update, context)

        elif callback_data.startswith("show_category_"):
            main_category_name = callback_data.replace("show_category_", "")
            category_content = COMMAND_CATEGORIES.get(main_category_name)
            if isinstance(category_content, dict):
                message, reply_markup = generate_subcategory_buttons(main_category_name, category_content)
                await query.edit_message_text(text=message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            else:
                logger.warning(f"❓ Unknown main category: {main_category_name}")
                await query.edit_message_text(f"{EMOJI['error']} Could not show main category '{main_category_name}'.")

        else:
            logger.warning(f"❓ Unknown callback: {callback_data}")
            await query.edit_message_text(f"{EMOJI['error']} Unbekannte Aktion: {callback_data}")

    except Exception as e:
        logger.error(f"❌ Exception in handle_button_click: {e}", exc_info=True)
        await query.edit_message_text(f"{EMOJI['error']} Unerwarteter Fehler beim Verarbeiten des Buttons.")

# --- Zusätzliche Handler ---

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, reply_markup = generate_main_category_buttons()
    if update.callback_query:
        await update.callback_query.message.edit_text(
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    logger.info(f"Startnachricht/Kategorien an Benutzer {update.effective_user.id} gesendet.")

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Leitet den Benutzer zur Start-Nachricht um, die die Kategorien anzeigt."""
    await handle_start(update, context)