import re
from typing import List


_SOFT_HYPHEN = "\u00ad"
_NBSP = "\u00a0"


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace(_SOFT_HYPHEN, "")
    s = s.replace(_NBSP, " ")
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def join_hyphenated(prev: str, cur: str) -> str:
    # "инфор-" + "мация" => "информация"
    if prev.endswith("-") and cur and cur[0].isalpha():
        return prev[:-1] + cur
    return prev + " " + cur


def is_probably_chapter_title(s: str) -> bool:
    t = s.strip()
    if not t:
        return False

    # Частые паттерны “глава/раздел”
    if re.match(r"^(глава|раздел|section|chapter)\b", t, flags=re.I):
        return True

    # "1." / "1.2" / "I." / "IV."
    if re.match(r"^(\d+(\.\d+){0,3}|[IVXLCDM]+)\b[.)]?\s+\S+", t, flags=re.I):
        return True

    # Все буквы верхнего регистра и не очень длинно
    if t.isupper() and 6 <= len(t) <= 120:
        return True

    return False
