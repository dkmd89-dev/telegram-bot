# handlers/check_artists_handler.py

# handlers/check_artists_handler.py

import re
from collections import defaultdict
from pathlib import Path
from config import Config
from helfer.artist_map import artist_rules, ARTIST_NAME_OVERRIDES
from helfer.genre_helfer import get_tags_from_file

from telegram import Update
from telegram.ext import ContextTypes
from html import escape as escape_html


def normalize_artist_name(raw_artist: str) -> str:
    """
    Normalisiert einen rohen Künstlernamen basierend auf definierten Regeln und Overrides.
    """
    for pattern, replacement in artist_rules.items():
        raw_artist = re.sub(pattern, replacement, raw_artist)
    cleaned = raw_artist.strip().lower()
    return ARTIST_NAME_OVERRIDES.get(cleaned, raw_artist.strip())


def scan_library_for_artists(library_dir: Path) -> dict:
    """
    Scannt die Musikbibliothek nach Künstlernamen und sammelt deren Varianten.
    """
    found_artists = defaultdict(set)

    # Stelle sicher, dass das Verzeichnis existiert und zugreifbar ist
    if not library_dir.is_dir():
        print(f"Warnung: Bibliothekspfad nicht gefunden oder kein Verzeichnis: {library_dir}")
        return found_artists

    for file in library_dir.rglob("*.m4a"):
        artist, _, _ = get_tags_from_file(file)
        if not artist:
            continue
        norm = normalize_artist_name(artist)
        found_artists[norm].add(artist.strip())

    return found_artists


def suggest_overrides(artist_dict: dict) -> dict:
    """
    Schlägt neue Einträge für ARTIST_NAME_OVERRIDES vor, basierend auf Varianten.
    """
    suggestions = {}
    for normalized, variants in artist_dict.items():
        for variant in variants:
            variant_key = variant.strip().lower()
            if variant_key not in ARTIST_NAME_OVERRIDES or ARTIST_NAME_OVERRIDES[variant_key] != normalized:
                if variant.strip() != normalized and variant_key != normalized:
                    suggestions[variant_key] = normalized
    return suggestions


async def handle_check_artists(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Führt einen Check der Künstlernamen in der Bibliothek durch und schickt das Ergebnis.
    Diese Funktion erwartet 'update' und 'context' als Argumente.
    """
    if update.message:
        await update.message.reply_text("🔎 Starte den Künstler-Check, dies kann einen Moment dauern...")

    artist_data = scan_library_for_artists(Config.LIBRARY_DIR)
    suggestions = suggest_overrides(artist_data)

    output_lines = []

    output_lines.append("🔎 <b>Artist-Mapping-Check</b>\n")
    output_lines.append("<b>🎭 Varianten je Künstler:</b>")

    for norm, variants in sorted(artist_data.items()):
        # HIER: escaped_norm verwenden, um HTML-Sonderzeichen zu maskieren
        escaped_norm = escape_html(norm) 
        if len(variants) > 1:
            # Auch hier: Jede Variante maskieren
            escaped_variants = [escape_html(v) for v in sorted(variants)]
            joined = ", ".join(escaped_variants)
            output_lines.append(f"• <code>{escaped_norm}</code>: {joined}")
        else:
            # Maskiere die einzelne Variante
            escaped_variant = escape_html(list(variants)[0])
            output_lines.append(f"• <code>{escaped_norm}</code>: {escaped_variant}")

    if suggestions:
        output_lines.append("\n<b>🧠 Mapping-Vorschläge (für ARTIST_NAME_OVERRIDES):</b>")
        for raw, norm in sorted(suggestions.items(), key=lambda item: item[0]):
            # Maskiere auch hier die Rohtexte und normalisierten Texte
            escaped_raw = escape_html(raw)
            escaped_norm = escape_html(norm)
            output_lines.append(f'"<code>{escaped_raw}</code>": "<code>{escaped_norm}</code>",')
    else:
        output_lines.append("\n✅ Keine neuen Mappings erforderlich!")

    output = "\n".join(output_lines)

    if update.message:
        for chunk in [output[i:i + 4000] for i in range(0, len(output), 4000)]:
            await update.message.reply_text(chunk, parse_mode="HTML")