# stats_handler.py

from api.navidrome_api import NavidromeAPI
from config import Config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from klassen.navidrome_stats import NavidromeStats
from logger import log_error, log_info, log_debug
from helfer.markdown_helfer import escape_md_v2
from emoji import EMOJI
from typing import List, Dict, Any
import time
from urllib.parse import quote
import requests
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
import logging
logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class StatsHandler:
    def __init__(self, update: Update):
        self.update = update
        self.stats_obj = NavidromeStats()
        self.PAGE_SIZE = 20  # Anzahl der Einträge pro Seite

    def _escape_text(self, text: Any) -> str:
        """Escape Text für Telegram MarkdownV2."""
        text = str(text).replace("\\", "\\\\")
        return escape_md_v2(text)

    def _write_scan_log(self, message: str):
        """Schreibt Nachrichten in das Scan-Log."""
        try:
            log_path = Path("/mnt/media/musiccenter/logs/scan.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"[{datetime.now().isoformat()}] {message}\n")
        except Exception as e:
            log_error(
                f"Fehler beim Schreiben in scan.log: {str(e)}", "StatsHandler")

    async def _get_paginated_response(self, lines: list[str], page: int, command: str, title: str, emoji: str, items_per_page: int = 30) -> tuple[str, InlineKeyboardMarkup]:
        """
        Erstellt eine paginierte Textantwort mit Inline-Buttons für Weiter-/Zurückblättern.

        Args:
            lines: Liste der Textzeilen.
            page: Aktuelle Seite (1-basiert).
            command: Name des Befehls für Callback (z. B. "indexes").
            title: Titel der Anzeige.
            emoji: Emoji zur optischen Darstellung.
            items_per_page: Anzahl der Zeilen pro Seite.

        Returns:
            Tuple aus formatiertem Text (MarkdownV2) und InlineKeyboardMarkup.
        """
        total_items = len(lines)
        total_pages = (total_items + items_per_page - 1) // items_per_page
        page = max(1, min(page, total_pages))

        start = (page - 1) * items_per_page
        end = start + items_per_page
        page_lines = lines[start:end]

        text = f"{emoji} *{escape_md_v2(title)}*\n\n"
        text += "\n".join(page_lines)
        text += f"\n\n📄 Seite {page} von {total_pages}"

        buttons = []
        if page > 1:
            buttons.append(InlineKeyboardButton(
                "⬅️ Zurück", callback_data=f"page_{command}_{page - 1}"))
        if page < total_pages:
            buttons.append(InlineKeyboardButton(
                "➡️ Weiter", callback_data=f"page_{command}_{page + 1}"))

        reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
        return text, reply_markup

    async def handle_genres(self, context: ContextTypes.DEFAULT_TYPE):
        """Behandelt den /genres Befehl zur Anzeige aller Genres mit Paginierung."""
    
        user_id = self.update.effective_user.id if self.update.effective_user else "Unbekannt"
        logger.info(f"▶️ [handle_genres] gestartet für Benutzer {user_id}")
    
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error("No message context to reply to in handle_genres", "StatsHandler")
            return
    
        page = int(context.user_data.get("genres_page", 1))
        logger.debug(f"[handle_genres] Lade Seite {page} für Benutzer {user_id}")
    
        msg = await reply_target.reply_text(f"{EMOJI['processing']} Lade Genres\\.\\.\\.", parse_mode="MarkdownV2")
    
        try:
            logger.debug("[handle_genres] Starte API-Aufruf getGenres()")
            genres_data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: NavidromeAPI.make_request("getGenres")
            )
            logger.debug(f"[handle_genres] API-Antwort erhalten: {genres_data}")
    
            genres = genres_data.get("genres", {}).get("genre", [])
            if not genres:
                logger.info("[handle_genres] Keine Genres gefunden")
                await msg.edit_text(f"{EMOJI['warning']} Keine Genres gefunden\\.", parse_mode="MarkdownV2")
                return
    
            lines = []
            total_genres = 0
            for genre in genres:
                name = self._escape_text(genre.get("value", "Unbekanntes Genre"))
                count = genre.get("songCount", 0)
                lines.append(f"🎵 *{name}* ({count} Songs)")
                total_genres += 1
    
            logger.info(f"[handle_genres] {total_genres} Genres verarbeitet, {len(lines)} Zeilen erstellt")
    
            if not lines:
                logger.info("[handle_genres] Keine Einträge nach Verarbeitung")
                await msg.edit_text(f"{EMOJI['warning']} Keine Einträge verfügbar\\.", parse_mode="MarkdownV2")
                return
    
            response, reply_markup = await self._get_paginated_response(
                lines, page, "genres", "Genres", EMOJI['music']
            )
    
            logger.debug(f"[handle_genres] Paginierte Antwort erstellt für Seite {page}")
            await msg.edit_text(response, parse_mode="MarkdownV2", reply_markup=reply_markup)
    
            context.user_data["genres_page"] = page
            log_info(f"Genresliste für Seite {page} an Benutzer {user_id} gesendet", "StatsHandler")
    
        except Exception as e:
            logger.error(f"[handle_genres] Fehler: {str(e)}", exc_info=True)
            await msg.edit_text(f"{EMOJI['error']} Fehler: {self._escape_text(str(e))}", parse_mode="MarkdownV2")
            log_error(f"handle_genres: {str(e)}", "StatsHandler")

    async def handle_artists(self, context: ContextTypes.DEFAULT_TYPE):
        """Behandelt den /artists Befehl zur Anzeige aller Künstler mit Paginierung."""
        user_id = self.update.effective_user.id if self.update.effective_user else "Unbekannt"
        logger.info(f"[handle_artists] Start für Benutzer {user_id}")

        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_artists", "StatsHandler")
            return

        page = int(context.user_data.get("artists_page", 1))
        logger.debug(
            f"[handle_artists] Lade Seite {page} für Benutzer {user_id}")

        msg = await reply_target.reply_text(f"{EMOJI['processing']} Lade Künstlerliste\\.\\.\\.", parse_mode="MarkdownV2")

        try:
            logger.debug("[handle_artists] Starte API-Aufruf getArtists()")
            artists_data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: NavidromeAPI.make_request("getArtists")
            )

            logger.info(
                f"[handle_artists] API-Daten erhalten: {len(str(artists_data))} Zeichen")

            artists = artists_data.get("artists", {}).get("index", [])
            logger.info(
                f"[handle_artists] {len(artists)} Indexeinträge gefunden")

            if not artists:
                await msg.edit_text(f"{EMOJI['warning']} Keine Künstler gefunden\\.", parse_mode="MarkdownV2")
                return

            lines = []
            total_artists = 0
            for index in artists:
                for artist in index.get("artist", []):
                    name = self._escape_text(artist.get(
                        "name", "Unbekannter Künstler"))
                    album_count = self._escape_text(
                        artist.get("albumCount", 0))
                    lines.append(f"🎤 *{name}* \\({album_count} Alben\\)")
                    total_artists += 1

            logger.info(
                f"[handle_artists] {total_artists} Künstler insgesamt verarbeitet")

            if not lines:
                await msg.edit_text(f"{EMOJI['warning']} Keine Künstler gefunden\\.", parse_mode="MarkdownV2")
                return

            response, reply_markup = await self._get_paginated_response(
                lines, page, "artists", "Künstlerliste", EMOJI['artist']
            )
            await msg.edit_text(response, parse_mode="MarkdownV2", reply_markup=reply_markup)
            context.user_data["artists_page"] = page
            log_info(
                f"Künstlerliste für Seite {page} an Benutzer {user_id} gesendet", "StatsHandler")

        except Exception as e:
            error_msg = f"[handle_artists] Fehler: {str(e)}"
            logger.error(error_msg, exc_info=True)
            await msg.edit_text(f"{EMOJI['error']} Fehler beim Laden der Künstler\\.", parse_mode="MarkdownV2")
            log_error(error_msg, "StatsHandler")

    async def test_navidrome_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Testet die Navidrome API und gibt Feedback"""
        # Use a more flexible way to reply based on context
        reply_target = update.callback_query.message if update.callback_query else update.message
        if not reply_target:
            log_error("No message context to reply to in test_navidrome_api", "command_handler")
            return

        msg = await reply_target.reply_text(
            f"{EMOJI['processing']} Teste Navidrome API..."
        )
        try:
            try:
                ping_result = NavidromeAPI.make_request("ping")
                server_version = ping_result.get("serverVersion", "unbekannt")
                await msg.edit_text(
                    f"{EMOJI['processing']} API erreichbar (v{server_version})..."
                )
            except Exception as e:
                await msg.edit_text(
                    f"{EMOJI['error']} API nicht erreichbar\nFehler: {str(e)}"
                )
                return
            try:
                navidrome_stats_instance = NavidromeStats() # Create instance if not already passed/available
                now_playing = navidrome_stats_instance.get_now_playing() # Use instance method
                if not now_playing:
                    await msg.edit_text(
                        f"{EMOJI['warning']} API erreichbar aber keine aktiven Plays"
                    )
                    return
                await msg.edit_text(
                    f"{EMOJI['success']} API voll funktionsfähig\nAktive Plays: {len(now_playing)}"
                )
            except Exception as e:
                await msg.edit_text(
                    f"{EMOJI['warning']} API teilweise funktionsfähig\nNowPlaying-Fehler: {str(e)}"
                )
        except Exception as e:
            await msg.edit_text(f"{EMOJI['error']} Kritischer Testfehler: {str(e)}")


    async def get_navidrome_stats(self):
        """Holt Navidrome-Statistiken aus mehreren API-Endpunkten."""
        logger.info("[get_navidrome_stats] Starte Abfrage der Statistiken")
        
        try:
            logger.debug("[get_navidrome_stats] ➤ ping")
            ping = NavidromeAPI.make_request("ping")
            version = ping.get("serverVersion", "unknown")
            logger.info(f"[get_navidrome_stats] Server-Version: {version}")
    
            logger.debug("[get_navidrome_stats] ➤ getArtists")
            artists = NavidromeAPI.make_request("getArtists")
            artist_count = sum(len(index.get("artist", [])) for index in artists.get("artists", {}).get("index", []))
            logger.info(f"[get_navidrome_stats] Künstler gefunden: {artist_count}")
    
            logger.debug("[get_navidrome_stats] ➤ getAlbumList2")
            albums = NavidromeAPI.make_request(
                "getAlbumList2", {"type": "alphabeticalByArtist", "size": "500"}
            )
            song_count = sum(album.get("songCount", 0) for album in albums.get("albumList2", {}).get("album", []))
            logger.info(f"[get_navidrome_stats] Song-Anzahl berechnet: {song_count}")
    
            logger.debug("[get_navidrome_stats] ➤ getGenres")
            genres_response = NavidromeAPI.make_request("getGenres")
    
            if "genres" in genres_response and isinstance(genres_response["genres"], dict):
                genres = genres_response["genres"].get("genre", [])
                genre_count = len(genres)
                logger.info(f"[get_navidrome_stats] Genres gefunden: {genre_count}")
            else:
                logger.warning("[get_navidrome_stats] Keine Genres oder ungültiges Format")
                genre_count = 0
    
            logger.debug("[get_navidrome_stats] ➤ getScanStatus")
            scan = NavidromeAPI.make_request("getScanStatus")
            scan_status = scan.get("scanStatus", {})
            last_scan = scan_status.get("lastScan", "Unbekannt")
            scanning = scan_status.get("scanning", False)
            logger.info(f"[get_navidrome_stats] Letzter Scan: {last_scan}, Läuft: {scanning}")
    
            stats = {
                "server_version": version,
                "artist_count": artist_count,
                "song_count": song_count,
                "genre_count": genre_count,
                "last_scan": last_scan,
                "scanning": scanning,
            }
    
            logger.info(f"[get_navidrome_stats] ✅ Statistik erfolgreich gesammelt: {stats}")
            return stats
    
        except Exception as e:
            log_error(f"[get_navidrome_stats] Fehler: {str(e)}", "get_navidrome_stats")
            raise

    async def _execute_scan(self):
        """Führt einen vollständigen Navidrome-Rescan via Docker aus mit erweitertem Logging."""
        try:
            container_name = getattr(
                Config, "NAVIDROME_CONTAINER_NAME", "navidrome")
            cmd = [
                "docker", "exec", container_name, "/app/navidrome", "scan", "--full"
            ]
            log_info(
                f"Starte vollständigen Rescan: {' '.join(cmd)}", "StatsHandler")
            self._write_scan_log(
                f"Starte vollständigen Rescan: {' '.join(cmd)}")

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                msg = (
                    f"{EMOJI['scan']} *Rescan gestartet*\n"
                    f"```\n{result.stdout.strip()}\n```"
                )
                log_info(
                    f"Rescan erfolgreich: {result.stdout.strip()}", "StatsHandler")
                self._write_scan_log(
                    f"Rescan erfolgreich: {result.stdout.strip()}")
                return True, msg
            else:
                error_msg = (
                    f"{EMOJI['error']} *Scan fehlgeschlagen*\n"
                    f"```\n{result.stderr.strip()}\n```"
                )
                log_error(
                    f"Scan-Fehler: {result.stderr.strip()}", "StatsHandler")
                self._write_scan_log(f"Scan-Fehler: {result.stderr.strip()}")
                return False, error_msg

        except subprocess.TimeoutExpired:
            log_error("Scan-Timeout (5 Minuten) erreicht", "StatsHandler")
            self._write_scan_log("FEHLER: Scan-Timeout (5 Minuten) erreicht")
            return (
                False,
                f"{EMOJI['warning']} Scan dauert länger als 5 Minuten \\– bitte im Log prüfen\\.",
            )
        except Exception as e:
            log_error(f"Kritischer Fehler: {str(e)}", "StatsHandler")
            self._write_scan_log(f"FEHLER: Kritischer Fehler: {str(e)}")
            return False, f"{EMOJI['error']} *Systemfehler*: `{self._escape_text(str(e))}`"

    async def handle_navidrome_stats(self, context: ContextTypes.DEFAULT_TYPE):
        """Behandelt den /navidrome Befehl zur Anzeige von Navidrome-Statistiken."""
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_navidrome_stats", "StatsHandler")
            return

        msg = await reply_target.reply_text(f"{EMOJI['processing']} Navidrome-Statistiken werden geladen\\.\\.\\.")
        try:
            stats = await self.get_navidrome_stats()
            text = (
                f"{EMOJI['navidrome']} *Navidrome Server*\n"
                f"ℹ️ Version: {self._escape_text(stats['server_version'])}\n"
                f"🎤 {EMOJI['artist']} Künstler: {self._escape_text(stats['artist_count'])}\n"
                f"🎵 {EMOJI['song']} Songs: {self._escape_text(stats['song_count'])}\n"
                f"🎵 {EMOJI['genres']} Genres: {self._escape_text(stats['genre_count'])}\n"
                f"📡 {EMOJI['scan']} Letzter Scan: {self._escape_text(stats['last_scan'])}\n"
                f"🟢 Status: {self._escape_text('Scan läuft' if stats['scanning'] else 'Bereit')}"
            )
            await msg.edit_text(text, parse_mode="MarkdownV2")
        except Exception as e:
            await msg.edit_text(
                f"{EMOJI['error']} Fehler: {self._escape_text(str(e))}",
                parse_mode="MarkdownV2",
            )
            log_error(f"handle_navidrome_stats: {str(e)}", "StatsHandler")

    async def handle_indexes(self, context: ContextTypes.DEFAULT_TYPE):
        """Behandelt den /indexes Befehl zur Anzeige von Künstlern und Alben mit Paginierung."""
    
        user_id = self.update.effective_user.id if self.update.effective_user else "Unbekannt"
        logger.info(f"▶️ [handle_indexes] gestartet für Benutzer {user_id}")
    
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error("No message context to reply to in handle_indexes", "StatsHandler")
            return
    
        page = int(context.user_data.get("indexes_page", 1))
        logger.debug(f"[handle_indexes] Lade Seite {page} für Benutzer {user_id}")
    
        msg = await reply_target.reply_text(f"{EMOJI['processing']} Lade Künstler und Alben\\.\\.\\.", parse_mode="MarkdownV2")
        
        try:
            logger.debug("[handle_indexes] Starte API-Aufruf getIndexes()")
            indexes_data = await asyncio.get_event_loop().run_in_executor(
                None, lambda: NavidromeAPI.make_request("getIndexes")
            )
            logger.debug(f"[handle_indexes] API-Antwort erhalten: {indexes_data}")
    
            indexes = indexes_data.get("indexes", {}).get("index", [])
            if not indexes:
                logger.info("[handle_indexes] Keine Künstler oder Alben gefunden")
                await msg.edit_text(f"{EMOJI['warning']} Keine Künstler oder Alben gefunden\\.", parse_mode="MarkdownV2")
                return
    
            lines = []
            total_artists = 0
            total_albums = 0
    
            for index in indexes:
                for artist in index.get("artist", []):
                    name = self._escape_text(artist.get("name", "Unbekannter Künstler"))
                    lines.append(f"🎤 *{name}*")
                    total_artists += 1
                    for album in artist.get("album", []):
                        album_name = self._escape_text(album.get("title", "Unbekanntes Album"))
                        lines.append(f"  📀 {album_name}")
                        total_albums += 1
    
            logger.info(f"[handle_indexes] {total_artists} Künstler und {total_albums} Alben verarbeitet, {len(lines)} Zeilen erstellt")
    
            if not lines:
                logger.info("[handle_indexes] Keine Einträge nach Verarbeitung")
                await msg.edit_text(f"{EMOJI['warning']} Keine Einträge verfügbar\\.", parse_mode="MarkdownV2")
                return
    
            response, reply_markup = await self._get_paginated_response(
                lines, page, "indexes", "Künstler und Alben", EMOJI['album']
            )
    
            logger.debug(f"[handle_indexes] Paginierte Antwort erstellt für Seite {page}")
            await msg.edit_text(response, parse_mode="MarkdownV2", reply_markup=reply_markup)
    
            # Save current page
            context.user_data["indexes_page"] = page
            log_info(f"Künstler- und Albenliste für Seite {page} an Benutzer {user_id} gesendet", "StatsHandler")
    
        except Exception as e:
            logger.error(f"[handle_indexes] Fehler: {str(e)}", exc_info=True)
            await msg.edit_text(f"{EMOJI['error']} Fehler: {self._escape_text(str(e))}", parse_mode="MarkdownV2")
            log_error(f"handle_indexes: {str(e)}", "StatsHandler")

    async def handle_albumlist(self, context: ContextTypes.DEFAULT_TYPE):
        """Behandelt den /albumlist Befehl mit Auswahl der Kriterien."""
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_albumlist", "StatsHandler")
            return

        buttons = [
            [InlineKeyboardButton("Neueste", callback_data="albumlist_newest"),
             InlineKeyboardButton("Beliebte", callback_data="albumlist_frequent")],
            [InlineKeyboardButton("Zufällig", callback_data="albumlist_random"),
             InlineKeyboardButton("Höchstbewertet", callback_data="albumlist_highest")],
            [InlineKeyboardButton("Alphabetisch", callback_data="albumlist_alphabeticalByName"),
             InlineKeyboardButton(f"{EMOJI['help']} Zurück", callback_data="show_categories")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await reply_target.reply_text(
            f"{EMOJI['album']} *Albenliste auswählen:*\n\nWähle ein Kriterium:",
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )

    async def handle_albumlist_criteria(self, context: ContextTypes.DEFAULT_TYPE, type_param: str):
        """Behandelt die Albumliste mit spezifischem Kriterium."""
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_albumlist_criteria", "StatsHandler")
            return

        msg = await reply_target.reply_text(f"{EMOJI['processing']} Lade Alben \\({self._escape_text(type_param)}\\)\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            albums_data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: NavidromeAPI.make_request(
                    "getAlbumList2", {"type": type_param, "size": "20"})
            )
            albums = albums_data.get("albumList2", {}).get("album", [])
            if not albums:
                await msg.edit_text(f"{EMOJI['warning']} Keine Alben für Kriterium '{self._escape_text(type_param)}' gefunden\\.", parse_mode="MarkdownV2")
                return

            lines = []
            for album in albums:
                title = self._escape_text(
                    album.get("title", "Unbekanntes Album"))
                artist = self._escape_text(
                    album.get("artist", "Unbekannter Künstler"))
                year = self._escape_text(album.get("year", "N/A"))
                lines.append(f"📀 *{title}* \\({artist}, {year}\\)")

            response = (
                f"{EMOJI['album']} *Alben \\({self._escape_text(type_param.title())}\\):*\n\n"
                + "\n".join(lines)
            )
            await msg.edit_text(response, parse_mode="MarkdownV2")
        except Exception as e:
            await msg.edit_text(f"{EMOJI['error']} Fehler: {self._escape_text(str(e))}", parse_mode="MarkdownV2")
            log_error(
                f"handle_albumlist_criteria ({type_param}): {str(e)}", "StatsHandler")

    async def handle_genres(self, context: ContextTypes.DEFAULT_TYPE):
        """Behandelt den /genres Befehl zur Anzeige aller Genres."""
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_genres", "StatsHandler")
            return

        msg = await reply_target.reply_text(f"{EMOJI['processing']} Lade Genres\\.\\.\\.")
        try:
            genres_data = await asyncio.get_event_loop().run_in_executor(None, lambda: NavidromeAPI.make_request("getGenres"))
            genres = genres_data.get("genres", {}).get("genre", [])
            if not genres:
                await msg.edit_text(f"{EMOJI['warning']} Keine Genres gefunden\\.", parse_mode="MarkdownV2")
                return

            lines = []
            for genre in genres:
                name = self._escape_text(
                    genre.get("value", "Unbekanntes Genre"))
                song_count = self._escape_text(genre.get("songCount", 0))
                album_count = self._escape_text(genre.get("albumCount", 0))
                lines.append(
                    f"🎵 *{name}* \\({song_count} Songs, {album_count} Alben\\)")

            response = (
                f"{EMOJI['genres']} *Genres:*\n\n"
                + "\n".join(lines[:20])
                + (f"\n\n{EMOJI['warning']} Nur die ersten 20 Genres angezeigt\\." if len(lines) > 20 else "")
            )
            await msg.edit_text(response, parse_mode="MarkdownV2")
        except Exception as e:
            await msg.edit_text(f"{EMOJI['error']} Fehler: {self._escape_text(str(e))}", parse_mode="MarkdownV2")
            log_error(f"handle_genres: {str(e)}", "StatsHandler")

    async def handle_scan_command(self, context: ContextTypes.DEFAULT_TYPE):
        """Behandelt den /scan Befehl für einen Navidrome Bibliotheks-Scan."""
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_scan_command", "StatsHandler")
            return

        processing_msg = await reply_target.reply_text(f"{EMOJI['running']} Starte Scan\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            self._write_scan_log("DEBUG: Hole initiale Statistiken...")
            stats_initial = await self.get_navidrome_stats()
            self._write_scan_log(
                f"DEBUG: Initiale Stats erhalten: {stats_initial}")

            if stats_initial.get("scanning"):
                await processing_msg.edit_text(
                    f"{EMOJI['warning']} Ein Scan läuft bereits\\!",
                    parse_mode="MarkdownV2"
                )
                self._write_scan_log(
                    "Ein Scan lief bereits zum Startzeitpunkt.")
                return

            await processing_msg.edit_text(
                f"{EMOJI['scan']} Starte Navidrome Rescan über Docker\\.\n\n⏳ Warte auf Abschluss\\.\\.\\.",
                parse_mode="MarkdownV2"
            )
            self._write_scan_log("Navidrome Rescan über Docker gestartet.")

            self._write_scan_log("DEBUG: Rufe execute_scan auf...")
            scan_success, scan_message = await self._execute_scan()
            self._write_scan_log(
                f"DEBUG: execute_scan Ergebnis: success={scan_success}, message={scan_message}")

            if not scan_success:
                await processing_msg.edit_text(scan_message, parse_mode="MarkdownV2")
                return

            final_stats = None
            for attempt in range(1, 6):
                wait_time = attempt * 3
                self._write_scan_log(
                    f"DEBUG: Versuch {attempt}/5 - Warte {wait_time} Sekunden vor Stats-Abruf...")
                await asyncio.sleep(wait_time)

                self._write_scan_log(
                    f"DEBUG: Hole finale Statistiken (Versuch {attempt})...")
                stats_final = await self.get_navidrome_stats()
                self._write_scan_log(
                    f"DEBUG: Stats Versuch {attempt}: {stats_final}")

                if stats_final and isinstance(stats_final, dict):
                    songs_count = stats_final.get("song_count")
                    artists_count = stats_final.get("artist_count")
                    genre_count = stats_final.get("genre_count")

                    if (songs_count is not None and artists_count is not None and genre_count is not None and
                        isinstance(songs_count, (int, str)) and isinstance(artists_count, (int, str)) and
                        isinstance(genre_count, (int, str)) and
                        str(songs_count).isdigit() and str(artists_count).isdigit() and str(genre_count).isdigit() and
                            int(songs_count) >= 0 and int(artists_count) >= 0 and int(genre_count) >= 0):
                        final_stats = stats_final
                        self._write_scan_log(
                            f"DEBUG: Gültige Stats gefunden in Versuch {attempt}: Songs={songs_count}, Artists={artists_count}, Genres={genre_count}")
                        break
                    else:
                        self._write_scan_log(
                            f"DEBUG: Stats Versuch {attempt} - Ungültige Werte: Songs={songs_count}, Artists={artists_count}, Genres={genre_count}")
                else:
                    self._write_scan_log(
                        f"DEBUG: Stats Versuch {attempt} - Keine gültigen Stats erhalten: {stats_final}")

            if final_stats:
                songs = self._escape_text(final_stats.get("song_count", "N/A"))
                artists = self._escape_text(
                    final_stats.get("artist_count", "N/A"))
                genres = self._escape_text(
                    final_stats.get("genre_count", "N/A"))
                response = (
                    f"{EMOJI['done']} Scan abgeschlossen\\!\n"
                    f"📀 Songs: *{songs}*\n"
                    f"🎤 Künstler: *{artists}*\n"
                    f"🎵 Genres: *{genres}*"
                )
                self._write_scan_log(
                    f"Scan erfolgreich abgeschlossen: Songs={songs}, Artists={artists}, Genres={genres}")
            else:
                self._write_scan_log(
                    "WARNUNG: Keine gültigen finalen Stats erhalten - zeige Fallback-Nachricht")
                response = (
                    f"{EMOJI['done']} Scan abgeschlossen\\!\n"
                    f"⚠️ *Statistiken konnten nicht abgerufen werden*\n"
                    f"Der Scan wurde ausgeführt\\, aber die aktualisierten Zahlen sind nicht verfügbar\\."
                )

            await processing_msg.edit_text(response, parse_mode="MarkdownV2")

        except Exception as e:
            error_text = self._escape_text(str(e))
            error_msg = f"{EMOJI['error']} Fehler: `{error_text}`"
            log_error(
                f"Fehler in handle_scan_command: {str(e)}", "StatsHandler")
            self._write_scan_log(f"FEHLER in handle_scan_command: {str(e)}")
            try:
                await processing_msg.edit_text(text=error_msg, parse_mode="MarkdownV2")
            except Exception:
                await processing_msg.edit_text(f"{EMOJI['error']} Fehler beim Scan aufgetreten\\.")

    async def handle_top_songs(self, context: ContextTypes.DEFAULT_TYPE, period: str = "month"):
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_top_songs", "StatsHandler")
            return

        msg = await reply_target.reply_text(f"{EMOJI['processing']} Lade Top Songs\\.\\.\\.", parse_mode="MarkdownV2")

        try:
            stats = self.stats_obj.generate_stats(period)
            if not stats or not stats["top_songs"]:
                await msg.edit_text(f"{EMOJI['warning']} Keine Song\\-Daten verfügbar\\.", parse_mode="MarkdownV2")
                return

            lines = [
                f"{self._escape_text(idx+1)}\\. {self._escape_text(title)} \\({self._escape_text(count)} Plays\\)"
                for idx, (title, count) in enumerate(stats["top_songs"])
            ]
            response = (
                f"{EMOJI['topsongs']} *Top Songs \\({self._escape_text(period.title())}\\):*\n\n"
                + "\n".join(lines)
                + f"\n\n{EMOJI['statistics']} Gesamt Plays: {self._escape_text(stats['total_plays'])}"
            )
            await msg.edit_text(response, parse_mode="MarkdownV2")

            chart_path = self.stats_obj.create_chart(stats, "songs")
            with open(chart_path, "rb") as chart_file:
                await reply_target.reply_photo(photo=chart_file, caption=f"{EMOJI['topsongs']} Top Songs Visualisierung")
        except Exception as e:
            await msg.edit_text(f"{EMOJI['error']} Fehler: {self._escape_text(str(e))}", parse_mode="MarkdownV2")
            log_error(f"handle_top_songs: {e}", "StatsHandler")

    async def handle_playing(self, context: ContextTypes.DEFAULT_TYPE):
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_playing", "StatsHandler")
            return

        msg = await reply_target.reply_text(f"{EMOJI['processing']} Lade aktuelle Titel\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            now_playing = await self.get_now_playing()
            if not now_playing:
                await msg.edit_text(f"{EMOJI['warning']} Es wird aktuell nichts gespielt\\.", parse_mode="MarkdownV2")
                return

            response = [f"{EMOJI['music']} *Aktuell spielend:*"]
            for idx, track in enumerate(now_playing, 1):
                title = self._escape_text(track.get("title", "Unknown Title"))
                artist = self._escape_text(
                    track.get("artist", "Unknown Artist"))
                album = self._escape_text(
                    track.get("album", "")) if track.get("album") else ""
                player = self._escape_text(
                    track.get("player", "")) if track.get("player") else ""
                line = f"{self._escape_text(idx)}\\. *{title}* \\- *{artist}*"
                if album:
                    line += f" {EMOJI['album']} *{album}*"
                if player:
                    line += f" {EMOJI['player']} {player}"
                response.append(line)

            await msg.edit_text("\n\n".join(response), parse_mode="MarkdownV2")
        except Exception as e:
            await msg.edit_text(f"{EMOJI['error']} Fehler beim Abrufen der aktuellen Titel\\.", parse_mode="MarkdownV2")
            log_error(f"handle_playing error: {e}", "StatsHandler")

    async def get_now_playing(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """Holt aktuelle Titel aus Navidrome."""
        if use_cache and hasattr(self, "_last_fetch"):
            if time.time() - self._last_fetch < 5:
                return getattr(self, "_cached_result", [])

        try:
            params = {
                "u": Config.NAVIDROME_USER,
                "p": quote(Config.NAVIDROME_PASS),
                "v": "1.16.0",
                "c": "yt_music_bot",
                "f": "json",
            }
            url = f"{Config.NAVIDROME_URL.rstrip('/')}/rest/getNowPlaying.view"

            if HAS_HTTPX:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
            else:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

            entries = data.get("subsonic-response", {}
                               ).get("nowPlaying", {}).get("entry", [])
            if not isinstance(entries, list):
                entries = [entries] if entries else []

            result = []
            for entry in entries:
                result.append({
                    "title": entry.get("title", "Unknown Title"),
                    "artist": entry.get("artist", "Unknown Artist"),
                    "album": entry.get("album"),
                    "player": entry.get("playerName"),
                    "username": entry.get("username"),
                })

            if use_cache:
                self._last_fetch = time.time()
                self._cached_result = result

            return result
        except Exception as e:
            log_error(f"NowPlaying API Fehler: {e}", "StatsHandler")
            return []

    async def handle_top_artists(self, context: ContextTypes.DEFAULT_TYPE):
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_top_artists", "StatsHandler")
            return

        msg = await reply_target.reply_text(f"{EMOJI['processing']} Lade Top Künstler\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            stats = self.stats_obj.generate_stats("month")
            if not stats or not stats["top_artists"]:
                await msg.edit_text(f"{EMOJI['warning']} Keine Künstler\\-Daten verfügbar\\.", parse_mode="MarkdownV2")
                return

            lines = [
                f"{self._escape_text(idx+1)}\\. {self._escape_text(artist)} \\({self._escape_text(count)} Plays\\)"
                for idx, (artist, count) in enumerate(stats["top_artists"])
            ]
            response = (
                f"{EMOJI['topartists']} *Top Künstler \\(30 Tage\\):*\n\n"
                + "\n".join(lines)
                + f"\n\n{EMOJI['statistics']} Gesamt Plays: {self._escape_text(stats['total_plays'])}"
            )
            await msg.edit_text(response, parse_mode="MarkdownV2")

            chart_path = self.stats_obj.create_chart(stats, "artists")
            with open(chart_path, "rb") as chart_file:
                await reply_target.reply_photo(photo=chart_file, caption=f"{EMOJI['topartists']} Top Künstler Visualisierung")
        except Exception as e:
            await msg.edit_text(f"{EMOJI['error']} Fehler: {self._escape_text(str(e))}", parse_mode="MarkdownV2")
            log_error(f"handle_top_artists: {str(e)}", "StatsHandler")

    async def handle_last_played(self, context: ContextTypes.DEFAULT_TYPE):
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_last_played", "StatsHandler")
            return

        msg = await reply_target.reply_text(f"{EMOJI['processing']} Suche letzten Song\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            last_song = self.stats_obj.get_last_played_song()
            if not last_song:
                await msg.edit_text(f"{EMOJI['warning']} Keine Songs in der History gefunden\\.", parse_mode="MarkdownV2")
                return

            def esc(t): return self._escape_text(t or "")

            response = (
                f"{EMOJI['lastplayed']} *Zuletzt gespielt:*\n\n"
                f"🎵 *Titel:* `{esc(last_song.get('title'))}`\n"
                f"🎤 *Künstler:* `{esc(last_song.get('artist'))}`\n"
                f"💿 *Album:* `{esc(last_song.get('album'))}`\n"
                f"⏱️ *Dauer:* `{esc(last_song.get('duration'))} Sekunden`\n"
                f"📅 *Zeitpunkt:* `{esc(last_song.get('timestamp'))}`"
            )
            await msg.edit_text(response, parse_mode="MarkdownV2")
        except Exception as e:
            await msg.edit_text(f"{EMOJI['error']} Fehler: `{self._escape_text(str(e))}`", parse_mode="MarkdownV2")
            log_error(f"handle_last_played: {str(e)}", "StatsHandler")

    async def handle_month_review(self, context: ContextTypes.DEFAULT_TYPE):
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_month_review", "StatsHandler")
            return

        msg = await reply_target.reply_text(f"{EMOJI['processing']} Erstelle Monatsrückblick\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            stats = self.stats_obj.generate_stats("month")
            if not stats:
                await msg.edit_text(f"{EMOJI['warning']} Keine Daten verfügbar\\.", parse_mode="MarkdownV2")
                return

            esc = self._escape_text
            top_songs = [f"{esc(i+1)}\\. {esc(t)} \\({esc(c)} Plays\\)" for i,
                         (t, c) in enumerate(stats["top_songs"])]
            top_artists = [f"{esc(i+1)}\\. {esc(a)} \\({esc(c)} Plays\\)" for i,
                           (a, c) in enumerate(stats["top_artists"])]
            top_albums = [f"{esc(i+1)}\\. {esc(a)} \\({esc(c)} Plays\\)" for i,
                          (a, c) in enumerate(stats["top_albums"])]

            lines = [
                f"{EMOJI['calendar']} *Monatsrückblick \\(30 Tage\\):*",
                f"{EMOJI['statistics']} Gesamt Plays: {esc(stats['total_plays'])}",
                "",
                f"{EMOJI['trophy']} *Top Songs:*", *top_songs,
                "",
                f"{EMOJI['trophy']} *Top Künstler:*", *top_artists,
                "",
                f"{EMOJI['trophy']} *Top Alben:*", *top_albums,
            ]
            await msg.edit_text("\n".join(lines), parse_mode="MarkdownV2")

            with open(self.stats_obj.create_chart(stats, "songs"), "rb") as f1, \
                    open(self.stats_obj.create_chart(stats, "artists"), "rb") as f2:
                await reply_target.reply_photo(photo=f1, caption=f"{EMOJI['topsongs']} Top Songs des Monats")
                await reply_target.reply_photo(photo=f2, caption=f"{EMOJI['topartists']} Top Künstler des Monats")
        except Exception as e:
            await msg.edit_text(f"{EMOJI['error']} Fehler: {self._escape_text(str(e))}", parse_mode="MarkdownV2")
            log_error(f"handle_month_review: {str(e)}", "StatsHandler")

    async def handle_year_review(self, context: ContextTypes.DEFAULT_TYPE):
        reply_target = self.update.callback_query.message if self.update.callback_query else self.update.message
        if not reply_target:
            log_error(
                "No message context to reply to in handle_year_review", "StatsHandler")
            return

        msg = await reply_target.reply_text(f"{EMOJI['processing']} Erstelle Jahresrückblick\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            stats = self.stats_obj.generate_stats("year")
            if not stats:
                await msg.edit_text(f"{EMOJI['warning']} Keine Daten verfügbar\\.", parse_mode="MarkdownV2")
                return

            esc = self._escape_text
            top_songs = [f"{esc(i+1)}\\. {esc(t)} \\({esc(c)} Plays\\)" for i,
                         (t, c) in enumerate(stats["top_songs"])]
            top_artists = [f"{esc(i+1)}\\. {esc(a)} \\({esc(c)} Plays\\)" for i,
                           (a, c) in enumerate(stats["top_artists"])]
            top_albums = [f"{esc(i+1)}\\. {esc(a)} \\({esc(c)} Plays\\)" for i,
                          (a, c) in enumerate(stats["top_albums"])]

            lines = [
                f"{EMOJI['yearreview']} *Jahresrückblick \\(365 Tage\\):*",
                f"{EMOJI['statistics']} Gesamt Plays: {esc(stats['total_plays'])}",
                "",
                f"{EMOJI['trophy']} *Top Songs:*", *top_songs,
                "",
                f"{EMOJI['trophy']} *Top Künstler:*", *top_artists,
                "",
                f"{EMOJI['trophy']} *Top Alben:*", *top_albums,
            ]
            await msg.edit_text("\n".join(lines), parse_mode="MarkdownV2")

            with open(self.stats_obj.create_chart(stats, "songs"), "rb") as f1, \
                    open(self.stats_obj.create_chart(stats, "artists"), "rb") as f2:
                await reply_target.reply_photo(photo=f1, caption=f"{EMOJI['topsongs']} Top Songs des Jahres")
                await reply_target.reply_photo(photo=f2, caption=f"{EMOJI['topartists']} Top Künstler des Jahres")
        except Exception as e:
            await msg.edit_text(f"{EMOJI['error']} Fehler: {self._escape_text(str(e))}", parse_mode="MarkdownV2")
            log_error(f"handle_year_review: {str(e)}", "StatsHandler")
