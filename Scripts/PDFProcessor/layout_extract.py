from typing import List, Tuple, Optional
from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTTextContainer, LTTextLine, LTChar

from Scripts.Utils.logger import Logger
from .model import Line
from .text_utils import normalize_text


def _median(values: List[float], default: float) -> float:
    if not values:
        return default
    vs = sorted(values)
    n = len(vs)
    m = n // 2
    return vs[m] if n % 2 else (vs[m - 1] + vs[m]) / 2.0


def _extract_line_style(lt_line: LTTextLine) -> Tuple[float, bool]:
    # font_size = медиана размеров символов
    # is_bold = эвристика по имени шрифта (Bold/Black/Semibold)
    sizes: List[float] = []
    bold_hits = 0
    total_chars = 0

    for obj in lt_line:
        if isinstance(obj, LTChar):
            total_chars += 1
            if obj.size:
                sizes.append(float(obj.size))
            fn = (obj.fontname or "").lower()
            if "bold" in fn or "black" in fn or "semibold" in fn:
                bold_hits += 1

    font_size = _median(sizes, default=0.0)
    is_bold = (total_chars > 0 and (bold_hits / max(1, total_chars)) >= 0.2)
    return font_size, is_bold


def extract_lines_streaming(
    pdf_path: str,
    max_pages: Optional[int],
    logger: Logger,
) -> List[List[Line]]:
    """
    Возвращает pages_lines: list[page] -> list[Line]
    """
    laparams = LAParams(
        line_margin=0.2,
        word_margin=0.1,
        char_margin=2.0,
        detect_vertical=False,
    )

    pages: List[List[Line]] = []
    for page_idx, layout in enumerate(extract_pages(pdf_path, laparams=laparams)):
        if max_pages is not None and page_idx >= max_pages:
            break

        out: List[Line] = []
        for el in layout:
            if not isinstance(el, LTTextContainer):
                continue
            for obj in el:
                if not isinstance(obj, LTTextLine):
                    continue
                txt = normalize_text(obj.get_text())
                if not txt:
                    continue
                try:
                    font_size, is_bold = _extract_line_style(obj)
                    out.append(
                        Line(
                            text=txt,
                            x0=float(obj.x0), y0=float(obj.y0),
                            x1=float(obj.x1), y1=float(obj.y1),
                            font_size=font_size,
                            is_bold=is_bold,
                        )
                    )
                except Exception as e:
                    logger.error("Ошибка извлечения строки", e)

        # Сортировка: сверху вниз, слева направо
        out.sort(key=lambda ln: (-ln.y1, ln.x0))
        pages.append(out)

    return pages
