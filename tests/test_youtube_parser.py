# -*- coding: utf-8 -*-
"""
Unit-Tests für das Modul youtube_parser.

Diese Testsuite überprüft die Funktionalität der `parse_youtube_title` Funktion,
um sicherzustellen, dass YouTube-Titel korrekt in Künstler und Songtitel zerlegt werden.
"""

import unittest
from youtube_parser import parse_youtube_title

class TestYouTubeParser(unittest.TestCase):
    """
    Testklasse für die Funktion parse_youtube_title.
    
    Jede Methode in dieser Klasse repräsentiert einen spezifischen Testfall,
    der ein bestimmtes Format von YouTube-Titeln abdeckt.
    """

    def test_standard_title_with_video_tag(self):
        """Testet einen Standardtitel mit '(Official Video)' und eckigen Klammern."""
        title = "Ski Aggu, Sido - Mein Block (Official Video) [4K]"
        expected = {'artist': 'Ski Aggu, Sido', 'song_title': 'Mein Block', 'original_title': title}
        self.assertEqual(parse_youtube_title(title), expected)

    def test_title_without_delimiter(self):
        """Testet einen Titel ohne das Trennzeichen '-'."""
        title = "Beethovens 9. Symphonie"
        expected = {'artist': '', 'song_title': 'Beethovens 9. Symphonie', 'original_title': title}
        self.assertEqual(parse_youtube_title(title), expected)

    def test_title_with_music_video_suffix(self):
        """Testet einen Titel mit dem Zusatz '(Official Music Video)'."""
        title = "BAUSA - Was du Liebe nennst (Official Music Video)"
        expected = {'artist': 'BAUSA', 'song_title': 'Was du Liebe nennst', 'original_title': title}
        self.assertEqual(parse_youtube_title(title), expected)
        
    def test_title_with_pipe_and_feature(self):
        """Testet einen Titel, der ein Feature und einen senkrechten Strich enthält."""
        title = "Peter Fox - Zukunft Pink (feat. Inéz) | Official Video"
        expected = {'artist': 'Peter Fox', 'song_title': 'Zukunft Pink', 'original_title': title}
        self.assertEqual(parse_youtube_title(title), expected)

    def test_title_with_multiple_hyphens(self):
        """Testet, ob nur am ersten Bindestrich getrennt wird."""
        title = "Some Artist - My-Song-With-Hyphens"
        expected = {'artist': 'Some Artist', 'song_title': 'My-Song-With-Hyphens', 'original_title': title}
        self.assertEqual(parse_youtube_title(title), expected)

    def test_empty_title(self):
        """Testet das Verhalten bei einer leeren Zeichenkette als Eingabe."""
        title = ""
        expected = {'artist': '', 'song_title': '', 'original_title': ''}
        self.assertEqual(parse_youtube_title(title), expected)

    def test_none_title(self):
        """Testet das Verhalten bei 'None' als Eingabe."""
        title = None
        # Die Funktion erwartet einen String, aber wir prüfen auf robuste Handhabung.
        # Basierend auf der Implementierung sollte es einen TypeError geben,
        # aber die Funktion prüft auf `if not title`, was auch None abfängt.
        expected = {'artist': '', 'song_title': '', 'original_title': ''}
        self.assertEqual(parse_youtube_title(title), expected)

    def test_title_is_only_song(self):
        """Testet einen Titel, der nur aus dem Songtitel zu bestehen scheint."""
        title = "Smells Like Teen Spirit"
        expected = {'artist': '', 'song_title': 'Smells Like Teen Spirit', 'original_title': title}
        self.assertEqual(parse_youtube_title(title), expected)

    def test_complex_title_with_various_brackets(self):
        """Testet einen komplexen Titel mit verschiedenen Klammertypen und Zusätzen."""
        title = "Artist Name - Song Title [HQ Audio] (Music Video) | prod. by Producer"
        expected = {'artist': 'Artist Name', 'song_title': 'Song Title', 'original_title': title}
        self.assertEqual(parse_youtube_title(title), expected)

    def test_livestream_radio_title(self):
        """Testet einen Titel, der keinem typischen Musikformat entspricht."""
        title = "Lofi Hip Hop Radio 24/7 📚 chill beats to study/relax to"
        expected = {'artist': '', 'song_title': 'Lofi Hip Hop Radio 24/7 📚 chill beats to study/relax to', 'original_title': title}
        self.assertEqual(parse_youtube_title(title), expected)

    def test_title_with_feature_in_parentheses(self):
        """Testet einen Titel mit einem Feature-Gast in Klammern, das entfernt wird."""
        title = "Travis Scott - SICKO MODE (Audio) ft. Drake"
        # Die aktuelle Implementierung entfernt alles in Klammern, inkl. des Features.
        expected = {'artist': 'Travis Scott', 'song_title': 'SICKO MODE', 'original_title': title}
        self.assertEqual(parse_youtube_title(title), expected)

# Dieser Block ermöglicht das Ausführen der Tests direkt über die Kommandozeile.
if __name__ == '__main__':
    print("--- Starte Unit-Tests für den YouTube-Titel-Parser ---")
    unittest.main(verbosity=2)