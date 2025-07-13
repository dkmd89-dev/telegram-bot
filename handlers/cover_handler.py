import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from mutagen.mp4 import MP4

# Lokale Module
from logger import log_info, log_error, log_warning
from config import Config
from klassen.cover_fixer import CoverFixer
from klassen.musicbrainz_client import MusicBrainzClient
from klassen.genius_client import GeniusClient
from klassen.lastfm_client import LastFMClient
from klassen.clean_artist import CleanArtist
from klassen.title_cleaner import TitleCleaner
from klassen.youtube_client import YouTubeClient
from klassen.artist_map import ARTIST_RULES, ARTIST_OVERRIDES

async def handle_fixcovers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_target = update.callback_query.message if update.callback_query else update.message
    if not reply_target:
        log_error("Keine Nachricht zum Antworten in handle_fixcovers gefunden", "cover_handler")
        return

    msg = await reply_target.reply_text("🔍 Suche nach Audiodateien in der Bibliothek...")

    try:
        # Clients initialisieren
        artist_cleaner = CleanArtist()  # Keine Parameter nötig!
        musicbrainz_client = MusicBrainzClient(artist_cleaner)
        genius_client = GeniusClient(artist_cleaner)
        lastfm_client = LastFMClient()
        youtube_client = YouTubeClient()
        cover_fixer = CoverFixer(musicbrainz_client, genius_client, lastfm_client, debug=True)

        library_path = Path(Config.LIBRARY_DIR)
        audio_files = list(library_path.rglob("*.m4a"))
        total_files = len(audio_files)

        if total_files == 0:
            await msg.edit_text("🤷 Keine Audiodateien (.m4a) in der Bibliothek gefunden.")
            return

        fixed_covers = 0
        skipped_files = 0
        youtube_fallbacks = 0

        await msg.edit_text(f"📚 {total_files} Audiodateien gefunden. Beginne mit der Verarbeitung...")
        await asyncio.sleep(1)

        for idx, audio_path in enumerate(audio_files, 1):
            try:
                audio = MP4(audio_path)

                if not audio.get("covr"):  # ✅ Richtige Prüfung
                    title = audio.get("\xa9nam", ["Unbekannter Titel"])[0]
                    artist = audio.get("\xa9ART", ["Unbekannter Künstler"])[0]
                    album = audio.get("\xa9alb", ["Unbekanntes Album"])[0]

                    cleaned_title = TitleCleaner.clean_title(title, artist)
                    cleaned_artist = artist_cleaner.clean(artist)

                    log_info(f"🔍 Suche Cover für '{cleaned_artist}' - '{cleaned_title}'", "handle_fixcovers")
                    source = "Primär"

                    # Primäre Quellen abfragen
                    cover_data = await cover_fixer.fetch_cover(cleaned_title, cleaned_artist, album)

                    # Fallback: YouTube
                    if not cover_data:
                        log_warning(f"⚠️ Kein Cover über primäre Quellen. YouTube-Fallback: '{cleaned_title}'", "handle_fixcovers")
                        cover_data = await youtube_client.fetch_thumbnail(cleaned_title, cleaned_artist)
                        if cover_data:
                            source = "YouTube"

                    # Cover einbetten
                    if cover_data:
                        if cover_fixer.embed_cover(audio, cover_data):
                            audio.save()
                            fixed_covers += 1
                            if source == "YouTube":
                                youtube_fallbacks += 1
                            log_info(f"✅ Cover hinzugefügt via {source} für: {audio_path.name}", "handle_fixcovers")
                        else:
                            skipped_files += 1
                            log_warning(f"❌ embed_cover fehlgeschlagen für {audio_path.name}", "handle_fixcovers")
                    else:
                        skipped_files += 1
                        log_warning(f"❌ Kein Cover verfügbar für: {audio_path.name}", "handle_fixcovers")

                # Fortschritt aktualisieren
                if idx % 10 == 0 or idx == total_files:
                    percentage = (idx / total_files) * 100
                    progress_bar = "█" * int(percentage / 5) + "░" * (20 - int(percentage / 5))
                    progress_text = (
                        f"⏳ **Verarbeitung läuft...**\n\n"
                        f"`{progress_bar}` {percentage:.1f}%\n\n"
                        f"📁 Datei: {idx}/{total_files}\n"
                        f"✅ Gefixt: {fixed_covers} (davon {youtube_fallbacks} via YouTube)\n"
                        f"⏭️ Übersprungen: {skipped_files}"
                    )
                    try:
                        await msg.edit_text(progress_text, parse_mode='Markdown')
                        await asyncio.sleep(0.2)
                    except Exception:
                        pass

            except Exception as e:
                skipped_files += 1
                log_error(f"Fehler bei der Verarbeitung von {audio_path.name}: {e}", "handle_fixcovers")

        # Erfolgsquote berechnen
        success_rate = (fixed_covers / total_files) * 100 if total_files else 0

        # Abschlussmeldung
        final_message = (
            f"🎉 **Fertig!**\n\n"
            f"📦 **Überprüft:** {total_files} Dateien\n"
            f"✅ **Hinzugefügt:** {fixed_covers} Cover "
            f"(davon {youtube_fallbacks} via *YouTube*)\n"
            f"⏭️ **Übersprungen:** {skipped_files} Dateien\n"
            f"📊 **Erfolgsquote:** {success_rate:.1f}%"
        )
        await msg.edit_text(final_message, parse_mode='Markdown')

    except Exception as e:
        log_error(f"Ein schwerwiegender Fehler in handle_fixcovers: {e}", "cover_handler")
        await msg.edit_text(f"❌ **Fehler:**\n`{e}`")