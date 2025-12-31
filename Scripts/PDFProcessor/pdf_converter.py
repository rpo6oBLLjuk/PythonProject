import os
import re
import json
from dataclasses import dataclass
from typing import List, Dict, Optional

import PyPDF2
import pdfplumber
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextLine, LTRect, LTFigure
from PIL import Image
from pdf2image import convert_from_path
import pytesseract

from Scripts.Utils.logger import Logger
from PySide6.QtCore import QThread, Signal

from Scripts.PDFProcessor.model import TextType, TextItem

POPPLER_PATH = r'Packages\\poppler-25.12.0\\Library\\bin'


# ----------------------------
# Worker thread
# ----------------------------
class PDFConverterWithStructureThread(QThread):
    progress = Signal(str)               # Status text
    page_ready = Signal(int, str)        # page_num, JSON list of items for page
    finished_conversion = Signal(str)    # JSON of whole document

    def __init__(self, pdf_path: str, temp_dir: str, max_pages: int):
        super().__init__()
        self.pdf_path = pdf_path
        self.temp_dir = temp_dir
        self.max_pages = max_pages
        self.logger = Logger(console=False)

    def run(self):
        self.logger.info("Запуск конвертации с новой структурой данных (type+text)")
        try:
            doc = convert_pdf_to_text_with_structure(
                self.pdf_path,
                self.temp_dir,
                self.logger,
                max_pages=self.max_pages,
                progress_signal=self.progress,
                page_signal=self.page_ready
            )
            result_json = json.dumps(doc, ensure_ascii=False)
            self.progress.emit("Конвертация завершена")
            self.finished_conversion.emit(result_json)
        except Exception as e:
            self.logger.error("Ошибка в потоке", e)
            self.progress.emit(f"Ошибка: {str(e)}")
            self.finished_conversion.emit("{}")


# ----------------------------
# Line-based extraction
# ----------------------------
@dataclass(frozen=True)
class _Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)


def _normalize_text(s: str) -> str:
    """Clean common PDF artifacts."""
    if not s:
        return ""
    s = s.replace("\u00ad", "")   # soft hyphen
    s = s.replace("\xa0", " ")    # NBSP
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def classify_text_block(text: str) -> TextType:
    """Keep your existing minimal heuristics (no font info)."""
    s = text.strip()

    if re.match(r"^\d+[\.\)]\s*", s):
        return "task_number"

    if re.match(r"^[A-Da-d][\.\)]\s*", s):
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


def _extract_lines(container: LTTextContainer, logger: Logger) -> List[_Line]:
    """Extract LTTextLine objects with geometry."""
    out: List[_Line] = []
    try:
        for obj in container:
            if isinstance(obj, LTTextLine):
                t = _normalize_text(obj.get_text())
                if not t:
                    continue
                out.append(_Line(
                    text=t,
                    x0=float(obj.x0), y0=float(obj.y0),
                    x1=float(obj.x1), y1=float(obj.y1),
                ))
    except Exception as e:
        logger.error("Ошибка извлечения строк (LTTextLine)", e)
    return out


def _lines_to_items(lines: List[_Line], logger: Logger) -> List[TextItem]:
    """Merge lines into paragraphs using vertical gap + indentation."""
    if not lines:
        return []

    # Top-down, then left-right
    lines = sorted(lines, key=lambda ln: (-ln.y1, ln.x0))

    heights = [ln.height for ln in lines if ln.height > 0]
    med_h = _median(heights, default=12.0)

    gap_threshold = med_h * 0.8
    indent_threshold = max(10.0, med_h)

    items: List[TextItem] = []
    buf: List[str] = []

    prev: Optional[_Line] = None
    prev_x0: Optional[float] = None

    nongroup = {"header", "subheader", "task_number", "answer_option", "table", "image_text"}

    def flush_paragraph():
        nonlocal buf
        if buf:
            text = "\n".join(buf).strip()
            if text:
                items.append(TextItem(type="paragraph", text=text))
            buf = []

    for ln in lines:
        t = ln.text.strip()
        if not t:
            continue

        t_type = classify_text_block(t)

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
                # hyphenation merge: "информа-" + "ционная" => "информационная"
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


def _page_text_items(page_layout, logger: Logger) -> List[TextItem]:
    """Extract all text items from a page layout using line geometry."""
    all_lines: List[_Line] = []
    for el in page_layout:
        if isinstance(el, LTTextContainer):
            all_lines.extend(_extract_lines(el, logger))

    return _lines_to_items(all_lines, logger)


# ----------------------------
# Images / OCR / Tables helpers (kept)
# ----------------------------
def crop_image(element: LTFigure, reader: PyPDF2.PdfReader, page_idx: int, temp_dir: str, logger: Logger) -> Optional[str]:
    """Crop figure area without mutating mediabox."""
    try:
        path = os.path.join(temp_dir, f"crop_{page_idx}_{hash(element)}.pdf")

        page = reader.pages[page_idx]
        page.cropbox.lower_left = (element.x0, element.y0)
        page.cropbox.upper_right = (element.x1, element.y1)

        writer = PyPDF2.PdfWriter()
        writer.add_page(page)

        with open(path, "wb") as f:
            writer.write(f)

        return path
    except Exception as e:
        logger.error("Ошибка обрезки изображения", e)
        return None


def pdf_to_image(pdf_path: str, temp_dir: str, logger: Logger) -> Optional[str]:
    try:
        images = convert_from_path(pdf_path, poppler_path=POPPLER_PATH)
        if images:
            img_path = os.path.join(temp_dir, f"image_{hash(pdf_path)}.png")
            images[0].save(img_path)
            return img_path
    except Exception as e:
        logger.error("Ошибка конвертации PDF в изображение", e)
    return None


def image_to_text(image_path: str, logger: Logger) -> str:
    try:
        img = Image.open(image_path)
        try:
            return pytesseract.image_to_string(img, lang="rus")
        except Exception:
            return pytesseract.image_to_string(img)
    except Exception as e:
        logger.error("Ошибка OCR", e)
        return ""


def extract_table(pdf_path: str, page_num: int, table_num: int, logger: Logger):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            tables = pdf.pages[page_num].extract_tables()
            if table_num < len(tables):
                return tables[table_num]
    except Exception as e:
        logger.error("Ошибка извлечения таблицы", e)
    return None


def table_to_string(table) -> str:
    if not table:
        return ""
    return "\n".join(
        "|" + "|".join(str(cell or "") for cell in row) + "|" for row in table
    )


# ----------------------------
# Main conversion
# ----------------------------
def convert_pdf_to_text_with_structure(
    pdf_path: str,
    temp_dir: str,
    logger: Logger,
    max_pages: Optional[int] = None,
    progress_signal=None,
    page_signal=None
) -> Dict[str, List[Dict[str, str]]]:
    """
    Document: dict page_key -> Page
    Page: list of {type, text}

    NOTE: Text extraction is now line-based (Step 3).
    """
    doc: Dict[str, List[Dict[str, str]]] = {}

    os.makedirs(temp_dir, exist_ok=True)

    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)

        layouts = list(extract_pages(pdf_path))
        if max_pages:
            layouts = layouts[:max_pages]

        total_pages = len(layouts)

        for page_idx, page_layout in enumerate(layouts):
            page_num = page_idx + 1

            if progress_signal:
                progress_signal.emit(f"Обработка страницы {page_num}/{total_pages}")

            # ranked elements top-down for figures/tables
            ranked = []
            for el in page_layout:
                if hasattr(el, "y1"):
                    ranked.append((el.y1, el))
            ranked.sort(key=lambda x: x[0], reverse=True)

            items: List[TextItem] = []

            # 1) text items via LTTextLine geometry
            items.extend(_page_text_items(page_layout, logger))

            # 2) images/tables (kept from previous version)
            table_idx = 0
            for _, el in ranked:
                if isinstance(el, LTFigure):
                    cropped_pdf = crop_image(el, reader, page_idx, temp_dir, logger)
                    if cropped_pdf:
                        image_path = pdf_to_image(cropped_pdf, temp_dir, logger)
                        if image_path:
                            text = image_to_text(image_path, logger).strip()
                            if text:
                                items.append(TextItem(type="image_text", text=text))

                elif isinstance(el, LTRect):
                    # WARNING: rect != table; preserved behavior
                    table = extract_table(pdf_path, page_idx, table_idx, logger)
                    if table:
                        items.append(TextItem(type="table", text=table_to_string(table)))
                        table_idx += 1

            page_list = [it.to_dict() for it in items if it.text and it.text.strip()]
            doc[f"page_{page_num}"] = page_list

            if page_signal:
                page_signal.emit(page_num, json.dumps(page_list, ensure_ascii=False))

    return doc
