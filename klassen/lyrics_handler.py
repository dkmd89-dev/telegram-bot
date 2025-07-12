import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from mutagen.mp4 import MP4

from config import Config
from klassen.genius_client import GeniusClient
from klassen.clean_artist import CleanArtist
from klassen.title_cleaner import TitleCleaner
from logger import log_info, log_warning, log_error

FAILED_LOG_PATH = Path(Config.LOG_DIR) / "failed_lyrics.txt"

async def handle_fixlyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_target = update.callback_query.message if update.callback_query else update.message
    if not reply_target:
        log_error("Keine Nachricht zum Antworten in handle_fixlyrics gefunden", "lyrics_handler")
        return

    msg = await reply_target.reply_text("🔍 Suche nach Audiodateien in der Bibliothek...", parse_mode='Markdown')

    try:
        artist_cleaner = CleanArtist(
            artist_rules=Config.METADATA_CONFIG["artist_rules"],
            artist_overrides=Config.ARTIST_NAME_OVERRIDES
        )
        genius_client = GeniusClient(artist_cleaner)
        title_cleaner = TitleCleaner()

        library_path = Path(Config.LIBRARY_DIR)
        audio_files = list(library_path.rglob("*.m4a"))
        total_files = len(audio_files)

        if total_files == 0:
            await msg.edit_text("🤷 Keine Audiodateien (.m4a) in der Bibliothek gefunden.", parse_mode='Markdown')
            return

        updated_files = 0
        failed_files = 0
        failed_entries = []

        await msg.edit_text(f"📚 {total_files} Audiodateien gefunden. Starte Verarbeitung...", parse_mode='Markdown')
        await asyncio.sleep(1)

        for idx, audio_path in enumerate(audio_files, 1):
            try:
                audio = MP4(audio_path)
                if "\xa9lyr" in audio and audio["\xa9lyr"]:
                    log_info(f"Skipping {audio_path.name}: Lyrics already present", "handle_fixlyrics")
                    continue

                artist = audio.get("\xa9ART", [None])[0]
                title = audio.get("\xa9nam", [None])[0]

                if not artist or not title:
                    reason = f"⛔ Kein Artist oder Titel vorhanden ({audio_path})"
                    log_warning(reason, "handle_fixlyrics")
                    failed_entries.append(f"{audio_path} — {reason}")
                    failed_files += 1
                    continue

                clean_artist = artist_cleaner.clean(artist)
                clean_title = title_cleaner.clean_title(title, artist=clean_artist)

                log_info(f"Verarbeite {clean_artist} - {clean_title}", "handle_fixlyrics")
                metadata = await genius_client.fetch_metadata(clean_title, clean_artist)

                # Fallback: Wenn nichts gefunden → Originaltitel probieren
                if not metadata.get("lyrics"):
                    log_info(f"Fallback: Suche erneut mit unbearbeitetem Titel '{title}'", "handle_fixlyrics")
                    metadata = await genius_client.fetch_metadata(title, clean_artist)

                lyrics = metadata.get("lyrics")
                if lyrics:
                    audio["\xa9lyr"] = lyrics
                    audio.save()
                    updated_files += 1
                    log_info(f"Lyrics hinzugefügt: {audio_path.name}", "handle_fixlyrics")
                else:
                    reason = f"❌ Keine Lyrics gefunden für {clean_artist} - {title}"
                    log_warning(reason, "handle_fixlyrics")
                    failed_entries.append(f"{audio_path} — {reason}")
                    failed_files += 1

                # Fortschritt anzeigen
                if idx % 10 == 0 or idx == total_files:
                    percentage = (idx / total_files) * 100
                    bar = "█" * int(percentage / 5) + "░" * (20 - int(percentage / 5))
                    text = (
                        f"⏳ **Verarbeitung läuft...**\n\n"
                        f"`{bar}` {percentage:.1f}%\n\n"
                        f"📁 Datei: {idx}/{total_files}\n"
                        f"✅ Hinzugefügt: {updated_files}\n"
                        f"❌ Fehlgeschlagen: {failed_files}"
                    )
                    try:
                        await msg.edit_text(text, parse_mode='Markdown')
                        await asyncio.sleep(0.2)
                    except Exception:
                        pass

            except Exception as e:
                reason = f"⚠ Fehler: {str(e)}"
                log_error(reason, "handle_fixlyrics")
                failed_entries.append(f"{audio_path} — {reason}")
                failed_files += 1

        # Fehlgeschlagene speichern
        if failed_entries:
            FAILED_LOG_PATH.write_text("\n".join(failed_entries), encoding="utf-8")
            log_info(f"{len(failed_entries)} Fehler in {FAILED_LOG_PATH.name} protokolliert.", "handle_fixlyrics")

        # Abschlussmeldung
        completion = (
            f"🎉 **Verarbeitung abgeschlossen!**\n\n"
            f"📁 Insgesamt verarbeitet: {total_files}\n"
            f"✅ Lyrics hinzugefügt: {updated_files}\n"
            f"❌ Fehlgeschlagen: {failed_files}"
        )
        await msg.edit_text(completion, parse_mode='Markdown')

    except Exception as e:
        error_msg = f"❌ Schwerer Fehler: {str(e)}"
        log_error(error_msg, "handle_fixlyrics")
        await msg.edit_text(error_msg, parse_mode='Markdown')