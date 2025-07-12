import re
from telegram import Update, Message
from telegram.ext import ContextTypes
from services.downloader import YoutubeDownloader
from logger import log_error, log_info
from helfer.markdown_helfer import escape_md_v2
from emoji import EMOJI
from typing import Dict, Any, Union

class DownloadHandler:
    def __init__(self, update: Update):
        self.update = update
        self.downloader = YoutubeDownloader(update)

    async def handle_youtube_links(self, context: ContextTypes.DEFAULT_TYPE):
        """Handler für direkt gesendete YouTube-Links."""
        if not self.update.message or not self.update.message.text:
            return
        text = self.update.message.text
        youtube_pattern = r"(https?://)?(www\.)?(youtube|youtu)\.(com|be)/.+"
        if re.match(youtube_pattern, text):
            msg = await self.update.message.reply_text(
                f"{EMOJI['download']} YouTube-Link erkannt, starte Download..."
            )
            try:
                result = await self.downloader.download_audio(text)
                processed_result = self.process_download_result(result)
                if processed_result["success"]:
                    await self.handle_download_success(msg, processed_result)
                else:
                    await self.handle_download_failure(msg, processed_result["error"])
            except Exception as e:
                error_msg = escape_md_v2(f"{EMOJI['error']} Fehler beim Download: {str(e)}")
                await msg.edit_text(error_msg, parse_mode="MarkdownV2")
                log_error(f"handle_youtube_links: {str(e)}", "DownloadHandler")

    async def handle_download(self, context: ContextTypes.DEFAULT_TYPE):
        """Behandelt den /download-Befehl zum Herunterladen von YouTube-Audios."""
        status_msg = await self.update.message.reply_text("Starte Download...")
        url = context.args[0] if context.args else None
        if not url:
            await status_msg.edit_text(
                "Bitte geben Sie eine URL an. Beispiel: /download https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            )
            return
        try:
            processed_result = await self.downloader.download_audio(url)
            if processed_result:
                await self.handle_download_success(status_msg, processed_result)
            else:
                await self.handle_download_failure(status_msg, "Der Download ergab kein Ergebnis.")
        except Exception as e:
            error_message = f"❌ Ein unerwarteter Fehler ist aufgetreten: {str(e)}"
            log_error(f"Unerwartete Ausnahme in handle_download: {str(e)}", context="DownloadHandler")
            await self.handle_download_failure(status_msg, error_message)

    def process_download_result(self, result: Union[Dict[str, Any], str, None]) -> Dict[str, Any]:
        """Verarbeitet das Ergebnis eines Downloads."""
        response = {
            "success": False,
            "error": None,
            "file_path": None,
            "title": "Unbekannter Titel",
            "filename": "unbekannte_datei",
        }
        if result is None:
            response["error"] = "Download lieferte kein Ergebnis zurück"
            return response
        if isinstance(result, dict):
            response.update(result)
            response["success"] = bool(result.get("success", False))
            if not response["success"] and not response["error"]:
                response["error"] = "Download fehlgeschlagen ohne Fehlermeldung"
            return response
        if isinstance(result, str):
            response["error"] = result
            return response
        response["error"] = "Unbekanntes Ergebnisformat"
        return response

    async def handle_download_success(self, status_msg: Message, result: Dict[str, Any]) -> None:
        """Behandelt erfolgreichen Download mit formatierter Nachricht."""
        log_info(f"Download erfolgreich: {result['title']}", "DownloadHandler")
        escaped_title = escape_md_v2(result['title'])
        escaped_filename = escape_md_v2(result['filename'])
        escaped_header = escape_md_v2("Download erfolgreich!")
        success_msg = (
            f"{EMOJI['success']} *{escaped_header}*\n\n"
            f"{EMOJI['music']} *Titel:* {escaped_title}\n"
            f"{EMOJI['file']} *Datei:* `{escaped_filename}`\n\n"
            f"{EMOJI['time']} Fertiggestellt\\!"
        )
        await status_msg.edit_text(success_msg, parse_mode="MarkdownV2")

    def is_probably_file_path(self, text: str) -> bool:
        """Hilfsfunktion zur Erkennung von Pfadangaben statt echter Fehlermeldung."""
        return (
            text.startswith("/") or
            "\\" in text or
            text.count("/") >= 2 or
            any(ext in text.lower() for ext in [".m4a", ".mp3", ".webm", ".wav"])
        )

    async def handle_download_failure(self, status_msg: Message, error_msg: str):
        """Sendet eine Fehlermeldung nach einem fehlgeschlagenen Download."""
        log_error(f"Download fehlgeschlagen: {error_msg}", "DownloadHandler")
        try:
            await status_msg.edit_text(
                f"❌ *Download fehlgeschlagen*\n\n"
                f"Fehler: `{error_msg}`\n\n"
                f"Bitte versuche es später erneut oder mit einem anderen Link.",
                parse_mode="Markdown"
            )
        except Exception as e:
            log_error(f"Fehler beim Senden der Download-Fehlermeldung: {str(e)}", "DownloadHandler")