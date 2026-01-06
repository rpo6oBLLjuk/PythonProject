from typing import List, Dict, Any, Optional, Tuple
from Scripts.Utils.logger import Logger
from .model import Line, Chapter, Paragraph
from .text_utils import normalize_text, is_probably_chapter_title


def _median(values: List[float], default: float) -> float:
    if not values:
        return default
    vs = sorted(values)
    n = len(vs)
    m = n // 2
    return vs[m] if n % 2 else (vs[m - 1] + vs[m]) / 2.0


def _estimate_body_font(lines: List[Line]) -> float:
    sizes = [ln.font_size for ln in lines if ln.font_size and 6.0 <= ln.font_size <= 30.0]
    return _median(sizes, default=10.0)


def _is_header_line(ln: Line, body_font: float) -> Tuple[bool, int]:
    """
    Возвращает (is_header, level)
    level: 1 = глава, 2 = подзаголовок
    """
    t = ln.text.strip()
    if not t:
        return False, 0

    # Прямые паттерны “глава/раздел” почти всегда уровень 1
    if is_probably_chapter_title(t) and (ln.font_size >= body_font + 1.5 or ln.is_bold):
        return True, 1

    # Крупнее основного текста
    if ln.font_size >= body_font + 2.0:
        return True, 1

    # Чуть крупнее + bold -> подзаголовок
    if ln.font_size >= body_font + 0.8 and ln.is_bold and len(t) <= 140:
        return True, 2

    # Очень короткая строка bold может быть заголовком
    if ln.is_bold and len(t) <= 80 and not t.endswith("."):
        return True, 2

    return False, 0


def _split_into_paragraphs(lines: List[Line]) -> List[List[Line]]:
    """
    Грубая геометрия: новый параграф при большом вертикальном разрыве или резком изменении отступа.
    """
    if not lines:
        return []

    heights = [ln.height for ln in lines if ln.height > 0]
    med_h = _median(heights, default=12.0)
    gap_thr = med_h * 0.8
    indent_thr = max(10.0, med_h)

    groups: List[List[Line]] = []
    cur: List[Line] = []
    prev: Optional[Line] = None
    prev_x0: Optional[float] = None

    for ln in lines:
        if prev is None:
            cur.append(ln)
            prev = ln
            prev_x0 = ln.x0
            continue

        gap = float(prev.y0 - ln.y1)
        new_para = gap > gap_thr

        if prev_x0 is not None and abs(float(ln.x0) - float(prev_x0)) > indent_thr:
            new_para = True

        if new_para and cur:
            groups.append(cur)
            cur = [ln]
        else:
            cur.append(ln)

        prev = ln
        prev_x0 = ln.x0

    if cur:
        groups.append(cur)

    return groups


def build_chapters_from_pages(pages_lines: List[List[Line]], logger: Logger) -> List[Chapter]:
    """
    Берём строки со всех страниц, ищем заголовки, режем на главы,
    внутри главы режем на параграфы, подцепляя подзаголовки.
    """
    # Плоский список строк
    all_lines: List[Line] = []
    for page in pages_lines:
        all_lines.extend(page)

    if not all_lines:
        return []

    body_font = _estimate_body_font(all_lines)

    chapters: List[Chapter] = []
    current_chapter: Optional[Chapter] = None
    pending_para_headers: List[str] = []
    pending_para_lines: List[Line] = []

    def flush_paragraph_into_chapter():
        nonlocal pending_para_lines, pending_para_headers, current_chapter
        if current_chapter is None:
            # Если текст пошёл раньше главы, создаём “безымянную”
            current_chapter = Chapter(title="Без главы", headers=[], paragraphs=[])
            chapters.append(current_chapter)

        if not pending_para_lines:
            pending_para_headers = []
            return

        # Собираем текст параграфа
        texts: List[str] = []
        for ln in pending_para_lines:
            t = ln.text.strip()
            if not t:
                continue
            if texts:
                # аккуратно склеиваем переносы
                last = texts[-1]
                if last.endswith("-") and t and t[0].isalpha():
                    texts[-1] = last[:-1] + t
                else:
                    texts.append(t)
            else:
                texts.append(t)

        para_text = normalize_text("\n".join(texts))
        if para_text:
            current_chapter.paragraphs.append(
                Paragraph(headers=pending_para_headers[:], text=para_text)
            )

        pending_para_lines = []
        pending_para_headers = []

    def flush_chapter(title_line: Optional[str]):
        nonlocal current_chapter
        # перед сменой главы закрываем текущий параграф
        flush_paragraph_into_chapter()

        title = (title_line or "").strip() or "Без названия"
        current_chapter = Chapter(title=title, headers=[title], paragraphs=[])
        chapters.append(current_chapter)

    for ln in all_lines:
        is_header, level = _is_header_line(ln, body_font)
        t = ln.text.strip()
        if not t:
            continue

        if is_header and level == 1:
            flush_chapter(t)
            continue

        if is_header and level == 2:
            # подзаголовок относится к следующему параграфу
            flush_paragraph_into_chapter()
            pending_para_headers.append(t)
            continue

        # обычный текст
        pending_para_lines.append(ln)

    # финализация
    flush_paragraph_into_chapter()

    return chapters


def build_structured_json(source_file: str, chapters: List[Chapter]) -> Dict[str, Any]:
    return {
        "source_file": source_file,
        "chapters": [ch.to_dict() for ch in chapters],
    }
