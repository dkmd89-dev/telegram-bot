from telegram import Update
from telegram.ext import ContextTypes
from pathlib import Path
from config import Config
from helfer.extract_info_from_file import extract_info
from metadata import process_metadata, write_metadata
from logger import log_info, log_warning

import asyncio

async def reprocess_library(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = await update.message.reply_text("🔁 Starte Reprocessing deiner .m4a-Library...")

    m4a_files = list(Path(Config.LIBRARY_DIR).rglob("*.m4a"))
    total = len(m4a_files)
    corrected = 0
    failed = 0

    for idx, file_path in enumerate(m4a_files, 1):
        info = extract_info(file_path)
        if not info:
            log_warning(f"⚠️ Konnte keine Info extrahieren aus: {file_path}")
            failed += 1
            continue

        try:
            metadata = await process_metadata(info)
            write_metadata(file_path, metadata)
            corrected += 1
            log_info(f"✅ Metadaten gesetzt für: {file_path.name}")
        except Exception as e:
            log_warning(f"❌ Fehler bei {file_path.name}: {e}")
            failed += 1

        if idx % 10 == 0:
            await message.edit_text(f"📦 Fortschritt: {idx}/{total} Dateien verarbeitet...")

    await message.edit_text(f"✅ Fertig! Verarbeitet: {total}, Erfolgreich: {corrected}, Fehlgeschlagen: {failed}")