from mutagen.mp4 import MP4
from pathlib import Path

def extract_info(file_path: Path) -> dict:
    """Extrahiert ein info-Dict aus .m4a-Datei ähnlich wie yt-dlp."""
    try:
        audio = MP4(file_path)
        tags = audio.tags

        title = tags.get("\xa9nam", [""])[0]
        artist = tags.get("\xa9ART", [""])[0]
        album = tags.get("\xa9alb", [""])[0]
        date = tags.get("\xa9day", [""])[0]
        genre = tags.get("\xa9gen", [""])[0]
        track_number = tags.get("trkn", [(1, 0)])[0][0]

        info = {
            "title": title,
            "artist": artist,
            "album": album,
            "upload_date": date,
            "uploader": artist,
            "track_number": track_number,
            "is_single": album.lower() == "single",
            "filepath": str(file_path),
        }

        return info
    except Exception as e:
        print(f"Fehler beim Lesen von {file_path}: {e}")
        return {}