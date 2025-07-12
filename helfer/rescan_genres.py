# Beispiel in deinem Telegram-Bot-Handler für /rescan_genres

import asyncio
from pathlib import Path
from config import Config
from typing import Union, Optional, List, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from helfer.genre_helfer import (
    get_tags_from_file,
    fetch_genre_from_apis,
    write_genre_to_file,
    setup_logger,
    ARTIST_GENRE_CACHE, # Cache direkt importieren, um ihn zu leeren
    process_all_navidrome_songs_for_genre_fixing, # <-- HIER NEU HINZUFÜGEN
)

# Logger speziell für diesen Handler einrichten
rescan_logger = setup_logger("genre_rescan", Config.LOG_DIR / "genre.log")

async def process_single_file(file_path: Path, index: int, total: int):
    """Verarbeitet eine einzelne Datei während des Rescans."""
    rescan_logger.info(f"[{index}/{total}] Verarbeite: {file_path.name}")
    
    # Der erste Rückgabewert von get_tags_from_file ist der Künstler, dann Album, dann Titel.
    # Da wir hier nur Künstler und Titel benötigen, können wir das Album ignorieren.
    artist, _, title = get_tags_from_file(file_path) 

    if not artist or not title:
        rescan_logger.warning(f"[{index}/{total}] ⚠️ Metadaten (Titel/Künstler) fehlen in {file_path.name}")
        return False

    genre = await fetch_genre_from_apis(title, artist)

    if genre:
        return write_genre_to_file(file_path, genre)
    else:
        # Fallback auf Künstler-Cache (falls die API mal nichts liefert, aber für den Künstler schon was bekannt ist)
        # Überprüfen, ob der Künstler im Cache ist und ob dieser einen gültigen Genre-Eintrag hat.
        if artist in ARTIST_GENRE_CACHE and ARTIST_GENRE_CACHE[artist]:
            fallback_genre = ARTIST_GENRE_CACHE[artist]
            rescan_logger.info(f"[{index}/{total}] 🔁 Kein neues Genre gefunden, Fallback auf Cache-Genre '{fallback_genre}' für Künstler '{artist}'")
            return write_genre_to_file(file_path, fallback_genre)

    rescan_logger.info(f"[{index}/{total}] ❌ Kein Genre für {artist} – {title} gefunden.")
    return False


async def rescan_genres_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram-Befehl zum Starten eines vollständigen Genre-Rescans."""
    await update.message.reply_text("🔁 Starte vollständigen Genre-Scan... Das kann eine Weile dauern.")
    
    # Cache leeren vor einem kompletten Rescan
    ARTIST_GENRE_CACHE.clear()

    library_path = Path(Config.LIBRARY_DIR)
    # Sicherstellen, dass nur M4A-Dateien gesucht werden
    m4a_files = list(library_path.rglob("*.m4a")) 
    total_files = len(m4a_files)

    if total_files == 0:
        await update.message.reply_text("Keine M4A-Dateien im Verzeichnis gefunden. Scan abgebrochen.")
        rescan_logger.info("Keine M4A-Dateien für den Scan gefunden.")
        return

    rescan_logger.info(f"📂 Starte Genre-Rescan für {total_files} Dateien...")

    tasks = [process_single_file(f, i + 1, total_files) for i, f in enumerate(m4a_files)]
    
    # Führen Sie die Aufgaben aus. asyncio.gather wartet, bis alle Aufgaben abgeschlossen sind.
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r)
    failed_count = total_files - success_count

    # Statistik-Nachricht senden
    stats_msg = (
        f"✅ <b>Genre-Scan abgeschlossen</b>\n"
        f"• Erfolgreich aktualisiert: {success_count}\n"
        f"• Fehlgeschlagen/Übersprungen: {failed_count}"
    )
    await update.message.reply_text(stats_msg, parse_mode='HTML')

    # NEU HINZUGEFÜGT: Aufruf der Navidrome-basierten Genre-Verarbeitung
    await update.message.reply_text("🚀 Starte zusätzliche Navidrome-basierte Genre-Analyse...")
    await process_all_navidrome_songs_for_genre_fixing()
    await update.message.reply_text("✨ Navidrome-Analyse abgeschlossen. Überprüfe die Logs für Details.")

# Dieser Handler müsste dann in Ihrem Haupt-Bot-Code registriert werden
# Beispiel:
# application.add_handler(CommandHandler("rescan_genres", rescan_genres_command))