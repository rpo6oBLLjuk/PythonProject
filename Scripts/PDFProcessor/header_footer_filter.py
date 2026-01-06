import re
from dataclasses import dataclass
from typing import List, Dict, Tuple, Set

from Scripts.Utils.logger import Logger
from .model import Line
from .text_utils import normalize_text


_PAGE_NUM_RE = re.compile(
    r"""^\s*
    (?:page\s*)?                 # "Page"
    (?:[-–—]?\s*)?
    (\d{1,4})                    # 1..9999
    (?:\s*(?:/|из|of)\s*\d{1,4})? # "1/10", "1 из 10", "1 of 10"
    (?:\s*[-–—]?\s*)?
    $""",
    re.IGNORECASE | re.VERBOSE,
)

_ROMAN_RE = re.compile(r"^\s*[ivxlcdm]+\s*$", re.IGNORECASE)


def _is_page_number_text(t: str) -> bool:
    s = normalize_text(t)
    if not s:
        return False
    if _PAGE_NUM_RE.match(s):
        return True
    # Иногда страницы нумеруют римскими (i, ii, iii)
    if _ROMAN_RE.match(s) and len(s) <= 8:
        return True
    # "- 3 -" или "— 3 —"
    s2 = s.strip()
    if re.match(r"^[-–—]\s*\d{1,4}\s*[-–—]$", s2):
        return True
    return False


def _page_y_bounds(page_lines: List[Line]) -> Tuple[float, float]:
    """
    Возвращает (y_min, y_max) по странице.
    Координаты pdfminer: origin снизу, но нам важно только относительное.
    """
    if not page_lines:
        return 0.0, 1.0
    y_min = min(ln.y0 for ln in page_lines)
    y_max = max(ln.y1 for ln in page_lines)
    # защита от нулевой высоты
    if y_max <= y_min:
        y_max = y_min + 1.0
    return y_min, y_max


def _in_top_band(ln: Line, y_min: float, y_max: float, band_ratio: float) -> bool:
    h = (y_max - y_min)
    top_cut = y_max - h * band_ratio
    return ln.y1 >= top_cut


def _in_bottom_band(ln: Line, y_min: float, y_max: float, band_ratio: float) -> bool:
    h = (y_max - y_min)
    bottom_cut = y_min + h * band_ratio
    return ln.y0 <= bottom_cut


def _key_for_repeat(t: str) -> str:
    """
    Ключ для повторов: более агрессивная нормализация,
    чтобы "Документ 2025" и "Документ 2025 " считались одинаковыми.
    """
    s = normalize_text(t)
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def filter_headers_footers(
    pages_lines: List[List[Line]],
    logger: Logger,
    band_ratio: float = 0.12,
    repeat_ratio: float = 0.60,
    min_repeat_pages: int = 3,
    drop_page_numbers: bool = True,
) -> List[List[Line]]:
    """
    Удаляет повторяющиеся строки сверху/снизу (колонтитулы) и номера страниц.

    - band_ratio: доля высоты страницы, считаемая “верх/низ зоной”
    - repeat_ratio: строка считается колонтитулом, если встречается >= repeat_ratio страниц
    - min_repeat_pages: минимум страниц для признания колонтитулом
    """

    if not pages_lines:
        return pages_lines

    total_pages = len(pages_lines)

    # 1) Собираем частоты кандидатов (только верх/низ)
    freq: Dict[str, int] = {}

    for page in pages_lines:
        y_min, y_max = _page_y_bounds(page)

        # уникальные ключи на странице, чтобы одна и та же строка
        # не считалась дважды на одной странице
        seen_keys: Set[str] = set()

        for ln in page:
            if not ln.text or not ln.text.strip():
                continue

            in_band = _in_top_band(ln, y_min, y_max, band_ratio) or _in_bottom_band(ln, y_min, y_max, band_ratio)
            if not in_band:
                continue

            k = _key_for_repeat(ln.text)
            if not k:
                continue
            if k in seen_keys:
                continue

            seen_keys.add(k)
            freq[k] = freq.get(k, 0) + 1

    # 2) Определяем “повторяющиеся” строки
    threshold = max(min_repeat_pages, int(total_pages * repeat_ratio + 0.999))  # ceil
    repeated_keys = {k for k, c in freq.items() if c >= threshold}

    logger.info(
        f"Колонтитулы: найдено повторяющихся ключей {len(repeated_keys)} "
        f"(threshold={threshold}/{total_pages}, band_ratio={band_ratio})"
    )

    # 3) Фильтруем
    filtered_pages: List[List[Line]] = []

    for page_idx, page in enumerate(pages_lines, start=1):
        y_min, y_max = _page_y_bounds(page)
        out: List[Line] = []

        for ln in page:
            t = ln.text.strip()
            if not t:
                continue

            # выкидываем номера страниц (обычно низ, но иногда верх)
            if drop_page_numbers:
                if _is_page_number_text(t) and (
                    _in_bottom_band(ln, y_min, y_max, band_ratio) or _in_top_band(ln, y_min, y_max, band_ratio)
                ):
                    continue

            # выкидываем повторяющиеся строки, но только если они реально вверху/внизу
            in_band = _in_top_band(ln, y_min, y_max, band_ratio) or _in_bottom_band(ln, y_min, y_max, band_ratio)
            if in_band:
                k = _key_for_repeat(t)
                if k in repeated_keys:
                    continue

            out.append(ln)

        filtered_pages.append(out)

    return filtered_pages
