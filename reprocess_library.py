import asyncio
from pathlib import Path
from config import Config
from metadata import process_metadata  # ggf. anpassen
from helfer.extract_info_from_file import extract_info  # erzeugt info-dict aus Datei
from utils.metadata_writer import write_metadata  # schreibt final in Datei
from logger import log_info, log_warning

SUPPORTED_EXTENSION = ".m4a"

async def reprocess_file(file_path: Path):
    log_info(f"🔄 Verarbeite: {file_path}")
    
    info = extract_info(file_path)
    if not info:
        log_warning(f"⚠️ Konnte keine Info extrahieren aus: {file_path}")
        return

    try:
        metadata = await process_metadata(info)
        write_metadata(file_path, metadata)
        log_info(f"✅ Metadaten neu gesetzt für: {file_path.name}")
    except Exception as e:
        log_warning(f"❌ Fehler bei Datei {file_path.name}: {e}")

async def reprocess_library():
    library_path = Path(Config.LIBRARY_DIR)
    m4a_files = list(library_path.rglob(f"*{SUPPORTED_EXTENSION}"))
    
    total = len(m4a_files)
    log_info(f"🎧 Starte Reprocessing für {total} .m4a-Dateien in '{library_path}'")

    for idx, file_path in enumerate(m4a_files, 1):
        await reprocess_file(file_path)
        print(f"[{idx}/{total}] ✅ {file_path.relative_to(library_path)}")

    log_info("🏁 Reprocessing abgeschlossen.")

if __name__ == "__main__":
    asyncio.run(reprocess_library())