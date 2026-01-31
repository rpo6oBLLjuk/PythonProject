import re

# разные типы дефисов: -, ‐, ‒, –, —
HYPHENS = r'[-‐-‒–—]'

MARKER_RE = re.compile(r'^[®@Ф\\#]+\s*')


def strip_leading_markers(text: str) -> str:
    return MARKER_RE.sub('', text).strip()


def normalize_text(text: str) -> str:

    if not text:
        return ""

    # переносы слов: "вымыш-\nленная" → "вымышленная"
    text = re.sub(
        rf'{HYPHENS}\s*\n\s*',
        '',
        text
    )

    # нормализация переводов строк
    text = text.replace('\r\n', '\n')

    # более двух переносов → абзац
    text = re.sub(r'\n{3,}', '\n\n', text)

    # одиночные переносы внутри абзаца → пробел
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)

    # чистка пробелов
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r' *\n *', '\n', text)

    return text.strip()


def normalize_key(text: str) -> str:
    """
    Используется для TOC / сопоставлений.
    """
    if not text:
        return ""

    text = strip_leading_markers(text)
    text = re.sub(r'\.{2,}', ' ', text)
    text = re.sub(r'\s+\d{1,4}\s*$', '', text)
    text = normalize_text(text)

    text = (
        text.replace('«', '')
            .replace('»', '')
            .replace('"', '')
            .replace("'", '')
    )

    return text.strip()
