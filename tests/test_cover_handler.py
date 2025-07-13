import asyncio
from mutagen.mp4 import MP4
from klassen.cover_fixer import CoverFixer
from klassen.musicbrainz_client import MusicBrainzClient
from klassen.genius_client import GeniusClient
from klassen.lastfm_client import LastFMClient
from klassen.clean_artist import CleanArtist
from klassen.youtube_client import YouTubeClient
from helfer.artist_map import artist_rules, ARTIST_NAME_OVERRIDES
from config import Config
from logger import log_info, log_error

async def test_cover_handler():
    # Initialisiere Clients
    artist_cleaner = CleanArtist(artist_rules=artist_rules, artist_overrides=ARTIST_NAME_OVERRIDES)
    musicbrainz_client = MusicBrainzClient(artist_cleaner)
    genius_client = GeniusClient(artist_cleaner)
    lastfm_client = LastFMClient()
    youtube_client = YouTubeClient()
    cover_fixer = CoverFixer(musicbrainz_client, genius_client, lastfm_client, debug=True)

    # Teste eine Beispiel-Datei
    audio_path = "/mnt/media/musiccenter/library/Badchieff/Singles/2024 - NÜCHTERN.m4a"  # Ersetze mit tatsächlichem Pfad
    try:
        audio = MP4(audio_path)
        log_info(f"🔍 Datei: {audio_path}, covr: {bool(audio.get('covr'))}")
        if not audio.get("covr") or not audio["covr"][0]:
            title = audio.get("\xa9nam", ["Unbekannter Titel"])[0]
            artist = audio.get("\xa9ART", ["Unbekannter Künstler"])[0]
            album = audio.get("\xa9alb", ["Unbekanntes Album"])[0]
            log_info(f"🔍 Metadaten: Titel={title}, Künstler={artist}, Album={album}")

            # Teste Cover-Abfrage
            cover_data = await cover_fixer.fetch_cover(title, artist, album)
            if cover_data:
                log_info(f"✅ Cover gefunden ({len(cover_data)} Bytes)")
                with open("test_cover.jpg", "wb") as f:
                    f.write(cover_data)
                # Versuche, Cover einzubetten
                if cover_fixer.embed_cover(audio, cover_data):
                    audio.save()
                    log_info("✅ Cover erfolgreich eingebettet")
                else:
                    log_error("❌ Fehler beim Einbetten des Covers")
            else:
                log_error("❌ Kein Cover gefunden")
        else:
            log_info("✅ Cover bereits vorhanden")
    except Exception as e:
        log_error(f"❌ Fehler bei der Verarbeitung: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_cover_handler())