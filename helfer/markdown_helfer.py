# yt_music_bot/utils/markdown_helfer.py

def escape_md_v2(text: str) -> str:
    """
    Escaped einen Text gemäß Telegram MarkdownV2-Spezifikation.
    Siehe: https://core.telegram.org/bots/api#markdownv2-style

    Folgende Zeichen müssen escaped werden:
    '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!', '\'
    """
    if not isinstance(text, str):
        text = str(text)

    # Das Backslash-Zeichen muss zuerst escapet werden,
    # da es selbst als Escape-Zeichen für die anderen Sonderzeichen dient.
    # Andernfalls würde ein vorhandener Backslash im Originaltext falsch interpretiert.
    text = text.replace('\\', '\\\\')

    reserved_chars = [
        '_', '*', '[', ']', '(', ')', '~', '`',
        '>', '#', '+', '-', '=', '|', '{', '}',
        '.', '!'
    ]

    for char in reserved_chars:
        text = text.replace(char, f'\\{char}')

    return text