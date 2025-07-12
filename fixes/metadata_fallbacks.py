import logging
from pathlib import Path
from config import Config

# 📁 Eigener Logger für Fallbacks
fallback_log_file = Path(Config.LOG_DIR) / "fixes.log"
fallback_log_file.parent.mkdir(parents=True, exist_ok=True)

fallback_logger = logging.getLogger("MetadataFallbacks")
fallback_logger.setLevel(logging.DEBUG)

if not fallback_logger.handlers:
    handler = logging.FileHandler(fallback_log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
    fallback_logger.addHandler(handler)


def fix_metadata_fallbacks(metadata: dict, info: dict) -> dict:
    """
    Ergänzt fehlende oder generische Felder in Metadaten.
    Besonders nützlich für YouTube-Einzeltracks.
    """

    # 📀 Album Artist
    if not metadata.get("album_artist") or metadata["album_artist"].lower() in ["", "various artists", "unbekannter künstler"]:
        metadata["album_artist"] = metadata.get("artist", "")
        fallback_logger.info(f"🧼 album_artist auf '{metadata['album_artist']}' gesetzt")

    # 🖼️ Cover (YouTube-Thumbnail Fallback)
    if not metadata.get("cover_url"):
        thumbnail = info.get("thumbnail")
        if thumbnail:
            metadata["cover_url"] = thumbnail
            fallback_logger.info(f"🖼️ cover_url aus YouTube-Thumbnail gesetzt → {thumbnail}")
        else:
            fallback_logger.warning("⚠️ Kein Cover vorhanden – auch kein YouTube-Thumbnail gefunden")

    # 🎵 Titel sichern
    if not metadata.get("title"):
        metadata["title"] = info.get("title", "Unbekannter Titel")
        fallback_logger.warning(f"⚠️ Kein Titel – Fallback auf info['title']: '{metadata['title']}'")

    # 👤 Artist sichern
    if not metadata.get("artist"):
        metadata["artist"] = info.get("uploader", "Unbekannter Künstler")
        fallback_logger.warning(f"⚠️ Kein Artist – Fallback auf info['uploader']: '{metadata['artist']}'")

    # 📝 Lyrics fallback
    if not metadata.get("lyrics"):
        metadata["lyrics"] = "Instrumental"
        fallback_logger.info("📝 Keine Lyrics vorhanden – Fallback gesetzt: 'Instrumental'")

    # 🏷️ Tags fallback
    tags = metadata.get("tags", [])
    if not isinstance(tags, list) or not tags:
        metadata["tags"] = ["unknown"]
        fallback_logger.warning("🏷️ Keine Tags gefunden – Fallback gesetzt: ['unknown']")

    return metadata