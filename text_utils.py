import re

MARKER_RE = re.compile(r'^[®@Ф\\#]+\s+')


def strip_leading_markers(text: str) -> str:
    return MARKER_RE.sub('', text).strip()


def normalize_text(text: str) -> str:
    text = re.sub(r'-\s*\n\s*', '', text)
    text = text.replace('\r\n', '\n')
    text = re.sub(r'\n{2,}', '\n\n', text)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    return text.strip()


def normalize_key(text: str) -> str:
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
