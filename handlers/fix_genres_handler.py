# handlers/fix_genres_handler.py

import os
import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from config import Config
from helfer.genre_fixer import GenreFetcher
from logger import log_info, log_warning, log_error
from mutagen.mp4 import MP4

# Liste unerwünschter Genre-Werte
BAD_GENRES = {"", "unknown", "n/a", "na", "other", "misc", "none", None, "genre"}

async def handle_fix_genres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scant die Musikbibliothek und korrigiert schlechte oder fehlende Genres."""
    message = await update.message.reply_text("⏳ Genre-Fix wird vorbereitet...")

    genre_fetcher = GenreFetcher()

    files = list(Path(Config.LIBRARY_DIR).rglob("*.m4a"))
    total = len(files)
    fixed, skipped, failed = 0, 0, 0

    log_info(f"🎧 Starte Genre-Fix für {total} Dateien...")

    for idx, filepath in enumerate(files, 1):
        rel_path = filepath.relative_to(Config.LIBRARY_DIR)
        try:
            audio = MP4(filepath)
            current_genres = audio.tags.get("\xa9gen", [])
            genre_clean = current_genres[0].strip().lower() if current_genres else ""

            # ⛔ Skip, wenn Genre okay
            if genre_clean not in BAD_GENRES:
                skipped += 1
                continue

            title = audio.tags.get("\xa9nam", [""])[0]
            artist = audio.tags.get("\xa9ART", [""])[0]
            if not title or not artist:
                log_warning(f"❌ Datei übersprungen (fehlende Tags): {rel_path}")
                skipped += 1
                continue

            genre = await genre_fetcher.get_genre(title, artist)

            if not genre:
                log_warning(f"❌ Kein Genre gefunden für {rel_path}")
                failed += 1
                continue

            audio.tags["\xa9gen"] = [genre]
            audio.save()
            log_info(f"✅ Genre gesetzt für {rel_path}: {genre}")
            fixed += 1

        except Exception as e:
            log_error(f"❌ Fehler bei {rel_path}: {str(e)}")
            failed += 1

        # Optional: Fortschritt auch per Telegram
        if idx % 25 == 0 or idx == total:
            await message.edit_text(
                f"🔄 {idx}/{total} Dateien geprüft\n✅ {fixed} korrigiert\n⏭️ {skipped} übersprungen\n❌ {failed} fehlgeschlagen"
            )

    await message.edit_text(
        f"🏁 Genre-Fix abgeschlossen:\n\n📁 Dateien gesamt: {total}\n✅ Erfolgreich korrigiert: {fixed}\n⏭️ Übersprungen: {skipped}\n❌ Fehlgeschlagen: {failed}"
    )
    log_info(f"✅ Genre-Fix abgeschlossen: {fixed} erfolgreich, {skipped} übersprungen, {failed} fehlgeschlagen.")

# Für deine Bot-Integration:
def register_fix_genres_handler(application):
    application.add_handler(CommandHandler("fixgenres", handle_fix_genres))