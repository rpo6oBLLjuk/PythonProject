# Scripts/PDFProcessor/ocr_structure_builder.py
#
# OCR fallback for scanned PDFs (no text layer).
# Produces the SAME structured JSON format as the main parser:
#   { "source_file": "...", "chapters": [ { "title":..., "headers":[...], "paragraphs":[{"headers":[...],"text":"..."}] } ] }
#
# Intel-friendly notes:
# - Renders one page at a time (no giant list of images).
# - OCR in-memory (no PNG temp files).
# - Optional grayscale to speed up OCR a bit.
#
# Requirements:
# - poppler (pdftocairo) available (you already have POPPLER_BIN resolver)
# - tesseract available in PATH (pytesseract can see it)

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

from pdf2image import convert_from_path
from PIL import Image
import pytesseract

from Scripts.Utils.logger import Logger
from .text_utils import normalize_text, is_probably_chapter_title

from PIL import Image, ImageOps, ImageFilter



# -------------------------
# Heuristics / regex
# -------------------------

_PAGE_NUM_RE = re.compile(
    r"""^\s*
    (?:page\s*)?
    (?:[-–—]?\s*)?
    (\d{1,4})
    (?:\s*(?:/|из|of)\s*\d{1,4})?
    (?:\s*[-–—]?\s*)?
    $""",
    re.IGNORECASE | re.VERBOSE,
)

_ROMAN_RE = re.compile(r"^\s*[ivxlcdm]+\s*$", re.IGNORECASE)

# Subheader patterns: "1.2 ..." / "A) ..." / "I. ..." etc.
_SUBHEADER_RE = re.compile(r"^\s*(\d+(\.\d+){0,3}|[IVXLCDM]+|[A-Da-d])[\.)]\s+\S+", re.IGNORECASE)

# Common section keywords (ru/en)
_SECTION_WORD_RE = re.compile(r"^\s*(глава|раздел|параграф|section|chapter)\b", re.IGNORECASE)


def _is_page_number_line(line: str) -> bool:
    s = normalize_text(line)
    if not s:
        return False
    if _PAGE_NUM_RE.match(s):
        return True
    if _ROMAN_RE.match(s) and len(s.strip()) <= 8:
        return True
    if re.match(r"^[-–—]\s*\d{1,4}\s*[-–—]$", s.strip()):
        return True
    return False


def _looks_like_subheader(line: str) -> bool:
    s = normalize_text(line)
    if not s:
        return False
    if _SUBHEADER_RE.match(s):
        return True
    # short bold-ish looking headers aren't available in OCR; use text heuristics:
    # - short line, no period at end
    if 4 <= len(s) <= 90 and "\n" not in s and not s.endswith("."):
        # too shouty and short can be a header as well
        if s.isupper() and len(s) >= 8:
            return True
    return False


def _looks_like_chapter_title(line: str) -> bool:
    s = normalize_text(line)
    if not s:
        return False
    # Strong signals
    if _SECTION_WORD_RE.match(s):
        return True
    # Reuse the generic heuristic (works for ALLCAPS and numbered titles)
    return is_probably_chapter_title(s)


# -------------------------
# OCR rendering
# -------------------------

@dataclass
class OcrOptions:
    poppler_bin: str
    dpi: int = 250
    lang: str = "rus"
    grayscale: bool = True

    # На Windows poppler + многопоток = частая причина 0xC0000005.
    thread_count: int = 1

    # pdftocairo обычно ок, но если будет падать и так,
    # переключишь на False.
    use_pdftocairo: bool = True




def render_page(pdf_path: str, page_idx: int, opts: OcrOptions, logger: Logger) -> Optional[Image.Image]:
    try:
        images = convert_from_path(
            pdf_path,
            first_page=page_idx + 1,
            last_page=page_idx + 1,
            dpi=opts.dpi,
            fmt="png",
            use_pdftocairo=opts.use_pdftocairo,
            thread_count=opts.thread_count,
            poppler_path=opts.poppler_bin,
        )
        if not images:
            return None
        img = images[0]
        if opts.grayscale:
            img = img.convert("L")
        return img
    except Exception as e:
        logger.error("OCR: render_page error", e)
        return None


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    if img.mode != "L":
        img = img.convert("L")

    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)

    # бинаризация: под учебники обычно годится
    img = img.point(lambda p: 255 if p > 185 else 0)
    return img


def ocr_image(img: Image.Image, opts: OcrOptions, logger: Logger) -> str:
    try:
        img2 = preprocess_for_ocr(img)
        config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"

        try:
            return pytesseract.image_to_string(img2, lang=opts.lang, config=config)
        except Exception as e:
            logger.error("OCR: tesseract(lang) failed, fallback default", e)
            return pytesseract.image_to_string(img2, config=config)
    except Exception as e:
        logger.error("OCR: image_to_string error", e)
        return ""



# -------------------------
# Header/footer cleanup for OCR text
# -------------------------

def _split_lines(text: str) -> List[str]:
    # keep reasonably clean single lines
    t = text.replace("\r", "\n")
    lines = [normalize_text(x) for x in t.split("\n")]
    # drop empty-only lines but keep paragraph boundaries by marking empty later
    return lines


def strip_repeating_headers_footers(
    pages_text: List[str],
    top_n: int = 3,
    bottom_n: int = 3,
    repeat_ratio: float = 0.6,
    min_repeat_pages: int = 3,
) -> List[str]:
    """
    OCR-safe (no geometry): considers first/last N non-empty lines as potential header/footer.
    Removes those that repeat across many pages + removes page numbers.
    """
    total = len(pages_text)
    if total == 0:
        return pages_text

    # gather candidates per page
    freq: Dict[str, int] = {}

    def key(s: str) -> str:
        s = normalize_text(s).lower()
        s = re.sub(r"\s+", " ", s).strip()
        return s

    per_page_candidates: List[Tuple[List[str], List[str]]] = []
    for txt in pages_text:
        lines = [ln for ln in _split_lines(txt) if ln]
        top = lines[:top_n]
        bottom = lines[-bottom_n:] if bottom_n > 0 else []
        per_page_candidates.append((top, bottom))

        seen = set()
        for ln in top + bottom:
            if _is_page_number_line(ln):
                continue
            k = key(ln)
            if not k or k in seen:
                continue
            seen.add(k)
            freq[k] = freq.get(k, 0) + 1

    threshold = max(min_repeat_pages, int(total * repeat_ratio + 0.999))  # ceil
    repeated = {k for k, c in freq.items() if c >= threshold}

    cleaned_pages: List[str] = []
    for (top, bottom), txt in zip(per_page_candidates, pages_text):
        raw_lines = txt.replace("\r", "\n").split("\n")

        # Build a removal set for this page (original text match is fuzzy, so remove by normalized key)
        remove_keys = set()
        for ln in top + bottom:
            if _is_page_number_line(ln):
                remove_keys.add(key(ln))
                continue
            k = key(ln)
            if k in repeated:
                remove_keys.add(k)

        out_lines: List[str] = []
        for ln in raw_lines:
            nln = normalize_text(ln)
            if not nln:
                out_lines.append("")  # keep paragraph separation
                continue
            if key(nln) in remove_keys:
                continue
            if _is_page_number_line(nln):
                continue
            out_lines.append(nln)

        # re-normalize multiple empties
        joined = "\n".join(out_lines)
        joined = re.sub(r"\n{3,}", "\n\n", joined).strip()
        cleaned_pages.append(joined)

    return cleaned_pages


# -------------------------
# Build chapters/paragraphs from OCR text
# -------------------------

def build_chapters_from_ocr_text(source_file: str, pages_text: List[str]) -> Dict[str, Any]:
    """
    Text-only structure:
    - new chapter: strong chapter title line
    - paragraph boundary: blank line
    - paragraph headers: subheader-like lines, attached to next paragraph
    """
    chapters: List[Dict[str, Any]] = []
    current_ch: Optional[Dict[str, Any]] = None
    pending_headers: List[str] = []
    para_buf: List[str] = []

    def ensure_chapter(default_title: str = "Без главы"):
        nonlocal current_ch
        if current_ch is None:
            current_ch = {"title": default_title, "headers": [], "paragraphs": []}
            chapters.append(current_ch)

    def flush_paragraph():
        nonlocal para_buf, pending_headers
        text = normalize_text("\n".join(para_buf))
        para_buf = []
        if not text and not pending_headers:
            pending_headers = []
            return
        ensure_chapter()
        current_ch["paragraphs"].append({
            "headers": pending_headers[:],
            "text": text
        })
        pending_headers = []

    def start_new_chapter(title: str):
        nonlocal current_ch, pending_headers, para_buf
        flush_paragraph()
        t = normalize_text(title)
        if not t:
            t = "Без названия"
        current_ch = {"title": t, "headers": [t], "paragraphs": []}
        chapters.append(current_ch)
        pending_headers = []
        para_buf = []

    # Merge pages into a single stream while keeping blank lines
    stream_lines: List[str] = []
    for page_txt in pages_text:
        # keep blank lines for paragraph separation
        lines = page_txt.replace("\r", "\n").split("\n")
        for ln in lines:
            stream_lines.append(normalize_text(ln))
        # page boundary: add blank line (helps keep paragraphs from gluing)
        stream_lines.append("")
        stream_lines.append("")

    for ln in stream_lines:
        if not ln:
            # paragraph boundary
            flush_paragraph()
            continue

        # chapter title?
        if _looks_like_chapter_title(ln) and len(ln) <= 140:
            start_new_chapter(ln)
            continue

        # subheader line?
        if _looks_like_subheader(ln) and len(ln) <= 140:
            flush_paragraph()
            pending_headers.append(ln)
            continue

        # regular text
        para_buf.append(ln)

    flush_paragraph()

    return {"source_file": source_file, "chapters": chapters}


# -------------------------
# Public entry point
# -------------------------

def parse_scanned_pdf_ocr(
    pdf_path: str,
    total_pages: int,
    opts: OcrOptions,
    logger: Logger,
    progress_signal=None,
    cancel_check=None
) -> Dict[str, Any]:
    """
    OCRs pages and returns structured chapters JSON.
    """
    if cancel_check is None:
        cancel_check = lambda: False

    source_file = os.path.basename(pdf_path)

    pages_text: List[str] = []
    for page_idx in range(total_pages):
        if cancel_check():
            if progress_signal:
                progress_signal.emit("⛔ Отмена: OCR остановлен")
            break
        page_num = page_idx + 1
        if progress_signal:
            progress_signal.emit(f"OCR: рендер страницы {page_num}/{total_pages}")

        img = render_page(pdf_path, page_idx, opts, logger)


        if cancel_check():
            break

        if img is None:
            pages_text.append("")
            if progress_signal:
                progress_signal.emit(f"OCR: страница {page_num} -> render failed")
            continue

        if progress_signal:
            progress_signal.emit(f"OCR: распознавание текста {page_num}/{total_pages}")

        txt = ocr_image(img, opts, logger)
        txt = txt or ""
        pages_text.append(txt)

        if progress_signal:
            progress_signal.emit(f"OCR: страница {page_num} -> {len(txt)} символов")

    # Clean repeating headers/footers (OCR-safe)
    if progress_signal:
        progress_signal.emit("OCR: удаление повторяющихся колонтитулов/номеров страниц")
    cleaned_pages = strip_repeating_headers_footers(
        pages_text,
        top_n=3,
        bottom_n=3,
        repeat_ratio=0.6,
        min_repeat_pages=3,
    )

    if progress_signal:
        progress_signal.emit("OCR: построение структуры (главы/параграфы)")
    structured = build_chapters_from_ocr_text(source_file, cleaned_pages)

    return structured
