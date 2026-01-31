import re

MARKER_RE = re.compile(r'^[®@Ф\\#]+\s*')

def strip_leading_markers(text: str) -> str:
    return MARKER_RE.sub('', text).strip()


def normalize_text(text: str) -> str:
    text = re.sub(r'-\s*\n\s*', '', text)
    text = re.sub(r'\n{2,}', '\n\n', text)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()
