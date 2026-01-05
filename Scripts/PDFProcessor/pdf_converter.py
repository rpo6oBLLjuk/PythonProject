import os
import re
import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import PyPDF2
import pdfplumber
from pdfminer.high_level import extract_pages
from pdfminer.layout import (
    LTTextContainer,
    LTTextLine,
    LTFigure,
    LAParams,
)

from PIL import Image
from pdf2image import convert_from_path
import pytesseract

from Scripts.Utils.logger import Logger
from PySide6.QtCore import QThread, Signal

from Scripts.PDFProcessor.model import TextType, TextItem


# ============================================================
# Paths / config
# ============================================================

def _resolve_poppler_bin() -> str:
    # pdf_converter.py лежит в Scripts/PDFProcessor/
    # Проектный корень: Scripts/.. -> <root>
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(project_root, "Packages", "poppler-25.12.0", "Library", "bin")


POPPLER_BIN = _resolve_poppler_bin()

# Для производительности на Intel лучше МЕНЬШЕ I/O и меньше лишних проходов.
# - OCR_FIGURES: OCR по выделенным фигурам (дорого). Обычно выключено.
# - OCR_FALLBACK: OCR всей страницы, если текстового слоя нет.
OCR_FIGURES = False
OCR_FALLBACK = True

# pdf2image: pdftocairo обычно быстрее/стабильнее на Windows
PDF2IMAGE_KWARGS = dict(
    poppler_path=POPPLER_BIN,
    fmt="png",
    use_pdftocairo=True,
    thread_count=4,
)


# ============================================================
# Worker thread
# ============================================================

class PdfParseThread(QThread):
    """Background worker that parses a PDF into (type+text).

    Signals:
      - progress(str): status
      - page_ready(int, str): page_num + JSON(list[{type,text}])
      - finished(str): JSON(document dict)
    """

    progress = Signal(str)
    page_ready = Signal(int, str)
    finished = Signal(str)

    def __init__(self, pdf_path: str, temp_dir: str, max_pages: int):
        super().__init__()
        self.pdf_path = pdf_path
        self.temp_dir = temp_dir
        self.max_pages = max_pages
        self.logger = Logger(console=False)

    def run(self):
        self.logger.info("Запуск парсинга PDF (type+text)")
        try:
            doc = parse_pdf_document(
                pdf_path=self.pdf_path,
                temp_dir=self.temp_dir,
                logger=self.logger,
                max_pages=self.max_pages,
                progress_signal=self.progress,
                page_signal=self.page_ready,
            )
            self.progress.emit("Конвертация завершена")
            self.finished.emit(json.dumps(doc, ensure_ascii=False))
        except Exception as e:
            self.logger.error("Ошибка в потоке", e)
            self.progress.emit(f"Ошибка: {str(e)}")
            self.finished.emit("{}")


# ============================================================
# Text extraction (fast + geometry-aware)
# ============================================================

@dataclass(frozen=True)
class TextLineBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("­", "")  # soft hyphen
    s = s.replace(" ", " ")   # NBSP
    s = s.replace("\n", " ")
    s = re.sub("[ \t]+", " ", s)
    s = re.sub("\n{3,}", "\n\n", s)
    return s.strip()


def classify_text(text: str) -> TextType:
    s = text.strip()

    if re.match("^\d+[\.)]\s*", s):
        return "task_number"

    if re.match("^[A-Da-d][\.)]\s*", s):
        return "answer_option"

    if "\n" not in s and 5 <= len(s) <= 80 and not s.endswith("."):
        if s.isupper() and len(s) >= 8:
            return "header"
        return "subheader"

    return "regular"


def _median(values: List[float], default: float) -> float:
    if not values:
        return default
    vs = sorted(values)
    n = len(vs)
    m = n // 2
    if n % 2:
        return vs[m]
    return (vs[m - 1] + vs[m]) / 2.0


def extract_text_lines(container: LTTextContainer, logger: Logger) -> List[TextLineBox]:
    out: List[TextLineBox] = []
    try:
        for obj in container:
            if isinstance(obj, LTTextLine):
                t = normalize_text(obj.get_text())
                if not t:
                    continue
                out.append(TextLineBox(t, float(obj.x0), float(obj.y0), float(obj.x1), float(obj.y1)))
    except Exception as e:
        logger.error("Ошибка извлечения строк (LTTextLine)", e)
    return out


def build_items_from_lines(lines: List[TextLineBox]) -> List[TextItem]:
    """Merge visual lines into items.

    - Без шрифтов ориентируемся на геометрию.
    - Для скорости делаем один проход и минимум тяжёлых операций.
    """
    if not lines:
        return []

    lines = sorted(lines, key=lambda ln: (-ln.y1, ln.x0))

    heights = [ln.height for ln in lines if ln.height > 0]
    med_h = _median(heights, default=12.0)

    gap_threshold = med_h * 0.8
    indent_threshold = max(10.0, med_h)

    items: List[TextItem] = []
    buf: List[str] = []

    prev: Optional[TextLineBox] = None
    prev_x0: Optional[float] = None

    def flush_paragraph():
        nonlocal buf
        if not buf:
            return
        text = "\n".join(buf).strip()
        buf = []
        if text:
            items.append(TextItem(type="paragraph", text=text))

    for ln in lines:
        t = ln.text.strip()
        if not t:
            continue

        t_type = classify_text(t)

        new_para = False
        if prev is not None:
            gap = float(prev.y0 - ln.y1)
            if gap > gap_threshold:
                new_para = True

            if prev_x0 is not None and abs(float(ln.x0) - prev_x0) > indent_threshold:
                new_para = True

        if t_type in {"header", "subheader", "task_number", "answer_option"}:
            flush_paragraph()
            items.append(TextItem(type=t_type, text=t))
        else:
            if new_para:
                flush_paragraph()

            if buf:
                last = buf[-1]
                if last.endswith("-") and t and t[0].isalpha():
                    buf[-1] = last[:-1] + t
                else:
                    buf.append(t)
            else:
                buf.append(t)

        prev = ln
        prev_x0 = float(ln.x0)

    flush_paragraph()
    return items


def extract_page_text_items(page_layout, logger: Logger) -> List[TextItem]:
    lines: List[TextLineBox] = []
    for el in page_layout:
        if isinstance(el, LTTextContainer):
            lines.extend(extract_text_lines(el, logger))
    return build_items_from_lines(lines)


# ============================================================
# OCR / rendering (Intel-friendly: avoid disk I/O)
# ============================================================


def _ensure_tools(logger: Logger, progress_signal=None) -> None:
    if not os.path.isdir(POPPLER_BIN):
        msg = f"❌ Poppler bin не найден: {POPPLER_BIN}"
        logger.error(msg)
        if progress_signal:
            progress_signal.emit(msg)

    try:
        _ = pytesseract.get_tesseract_version()
    except Exception as e:
        msg = f"❌ Tesseract недоступен (pytesseract не видит tesseract.exe): {e}"
        logger.error(msg, e)
        if progress_signal:
            progress_signal.emit(msg)


def render_page_image(pdf_path: str, page_idx: int, logger: Logger) -> Optional[Image.Image]:
    """Render a single PDF page into a PIL image (in-memory)."""
    try:
        images = convert_from_path(
            pdf_path,
            first_page=page_idx + 1,
            last_page=page_idx + 1,
            **PDF2IMAGE_KWARGS,
        )
        return images[0] if images else None
    except Exception as e:
        logger.error("Ошибка рендера страницы в изображение", e)
        return None


def ocr_pil_image(img: Image.Image, logger: Logger) -> str:
    try:
        try:
            return pytesseract.image_to_string(img, lang="rus")
        except Exception as e:
            logger.error("Ошибка OCR (rus)", e)
            return pytesseract.image_to_string(img)
    except Exception as e:
        logger.error("Ошибка OCR", e)
        return ""


def _pdf_bbox_to_pil_crop(
    fig_bbox: Tuple[float, float, float, float],
    page_width: float,
    page_height: float,
    img_w: int,
    img_h: int,
) -> Tuple[int, int, int, int]:
    """Map PDF coords (origin bottom-left) -> PIL crop box (origin top-left)."""
    x0, y0, x1, y1 = fig_bbox
    sx = img_w / page_width
    sy = img_h / page_height

    left = int(max(0, min(img_w, x0 * sx)))
    right = int(max(0, min(img_w, x1 * sx)))

    top = int(max(0, min(img_h, img_h - (y1 * sy))))
    bottom = int(max(0, min(img_h, img_h - (y0 * sy))))

    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top

    return left, top, right, bottom


# ============================================================
# Tables (Intel-friendly: open pdfplumber once)
# ============================================================


def format_table_as_pipes(table) -> str:
    if not table:
        return ""
    return "\n".join("|" + "|".join(str(cell or "") for cell in row) + "|" for row in table)


# ============================================================
# Main conversion (streaming extract_pages)
# ============================================================


def parse_pdf_document(
    pdf_path: str,
    temp_dir: str,
    logger: Logger,
    max_pages: Optional[int] = None,
    progress_signal=None,
    page_signal=None,
) -> Dict[str, List[Dict[str, str]]]:
    """Parse a PDF into:

      Document: dict page_key -> Page
      Page: list of {type, text}

    Intel-friendly changes:
      1) Streaming `extract_pages` (без list(...))
      2) Pdfplumber open один раз на документ
      3) OCR без записи PNG на диск (in-memory)
      4) Fallback OCR только когда реально нет текста
      5) OCR фигур по умолчанию выключен (дорого)
    """

    doc: Dict[str, List[Dict[str, str]]] = {}
    os.makedirs(temp_dir, exist_ok=True)

    _ensure_tools(logger, progress_signal)

    # Total pages for progress
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        total_pdf_pages = len(reader.pages)

    total_pages = total_pdf_pages if max_pages is None else min(total_pdf_pages, max_pages)

    laparams = LAParams(
        line_margin=0.2,
        word_margin=0.1,
        char_margin=2.0,
        detect_vertical=False,
    )

    with pdfplumber.open(pdf_path) as pl_pdf:
        page_iter = extract_pages(pdf_path, laparams=laparams)

        for page_idx, page_layout in enumerate(page_iter):
            if page_idx >= total_pages:
                break

            page_num = page_idx + 1
            if progress_signal:
                progress_signal.emit(f"Обработка страницы {page_num}/{total_pages}")

            # 1) Text layer (fast)
            items: List[TextItem] = extract_page_text_items(page_layout, logger)

            # 2) Tables (pdfplumber уже открыт)
            try:
                tables = pl_pdf.pages[page_idx].extract_tables() or []
                for tbl in tables:
                    txt = format_table_as_pipes(tbl)
                    if txt.strip():
                        items.append(TextItem(type="table", text=txt))
            except Exception as e:
                logger.error(f"Ошибка извлечения таблиц на странице {page_num}", e)

            # Prepare ranked elements only if OCR_FIGURES is enabled
            ranked = None
            if OCR_FIGURES:
                ranked = []
                for el in page_layout:
                    if hasattr(el, "y1"):
                        ranked.append((el.y1, el))
                ranked.sort(key=lambda x: x[0], reverse=True)

            # 3) OCR for figures (optional)
            page_img: Optional[Image.Image] = None
            if OCR_FIGURES and ranked:
                page_width = float(getattr(page_layout, "width", 0.0) or page_layout.bbox[2])
                page_height = float(getattr(page_layout, "height", 0.0) or page_layout.bbox[3])

                for _, el in ranked:
                    if not isinstance(el, LTFigure):
                        continue

                    if page_img is None:
                        page_img = render_page_image(pdf_path, page_idx, logger)
                        if page_img is None:
                            break

                    img_w, img_h = page_img.size
                    crop_box = _pdf_bbox_to_pil_crop(
                        (float(el.x0), float(el.y0), float(el.x1), float(el.y1)),
                        page_width,
                        page_height,
                        img_w,
                        img_h,
                    )

                    l, t, r, b = crop_box
                    if (r - l) < 25 or (b - t) < 25:
                        continue

                    cropped = page_img.crop(crop_box)
                    text = normalize_text(ocr_pil_image(cropped, logger))
                    if text:
                        items.append(TextItem(type="image_text", text=text))

            # 4) Fallback OCR (only if page is empty)
            has_any_text = any(it.text and it.text.strip() for it in items)
            if OCR_FALLBACK and not has_any_text:
                if progress_signal:
                    progress_signal.emit(f"Текстовый слой не найден на стр. {page_num} -> OCR всей страницы")

                if page_img is None:
                    page_img = render_page_image(pdf_path, page_idx, logger)

                if page_img is not None:
                    ocr_text = normalize_text(ocr_pil_image(page_img, logger))
                    if ocr_text:
                        items.append(TextItem(type="image_text", text=ocr_text))
                        if progress_signal:
                            progress_signal.emit(f"OCR страницы {page_num}: {len(ocr_text)} символов")
                    else:
                        if progress_signal:
                            progress_signal.emit(f"OCR страницы {page_num}: пусто (0 символов)")

            page_list = [it.to_dict() for it in items if it.text and it.text.strip()]
            doc[f"page_{page_num}"] = page_list

            if page_signal:
                page_signal.emit(page_num, json.dumps(page_list, ensure_ascii=False))

    return doc
