import os
import json
from typing import Dict, Any, List, Callable, Optional

import PyPDF2
from PySide6.QtCore import QThread, Signal

from Scripts.Utils.logger import Logger

from .layout_extract import extract_lines_streaming
from .structure_builder import build_chapters_from_pages, build_structured_json
from .header_footer_filter import filter_headers_footers
from .ocr_structure_builder import parse_scanned_pdf_ocr, OcrOptions


def _resolve_poppler_bin() -> str:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(project_root, "Packages", "poppler-25.12.0", "Library", "bin")


def _empty_struct(source_file: str) -> Dict[str, Any]:
    return {"source_file": source_file, "chapters": []}


class PdfParseThread(QThread):
    progress = Signal(str)
    page_ready = Signal(int, str)   # page_num + JSON payload (progress/meta)
    finished = Signal(str)          # structured json

    def __init__(self, pdf_path: str, temp_dir: str, max_pages: int):
        super().__init__()
        self.pdf_path = pdf_path
        self.temp_dir = temp_dir
        self.max_pages = max_pages
        self.logger = Logger(console=False)

    def run(self):
        self.logger.info("Запуск парсинга PDF (главы/параграфы)")
        source_file = os.path.basename(self.pdf_path)

        try:
            # early cancel
            if self.isInterruptionRequested():
                self.progress.emit("⛔ Отменено до старта")
                self.finished.emit(json.dumps(_empty_struct(source_file), ensure_ascii=False))
                return

            doc = parse_pdf_document(
                pdf_path=self.pdf_path,
                temp_dir=self.temp_dir,
                logger=self.logger,
                max_pages=self.max_pages,
                progress_signal=self.progress,
                page_signal=self.page_ready,
                cancel_check=self.isInterruptionRequested,
            )

            if self.isInterruptionRequested():
                self.progress.emit("⛔ Отменено")
                self.finished.emit(json.dumps(_empty_struct(source_file), ensure_ascii=False))
                return

            self.progress.emit("Конвертация завершена")
            self.finished.emit(json.dumps(doc, ensure_ascii=False))

        except Exception as e:
            self.logger.error("Ошибка в потоке", e)
            self.progress.emit(f"Ошибка: {str(e)}")
            self.finished.emit(json.dumps(_empty_struct(source_file), ensure_ascii=False))


def parse_pdf_document(
    pdf_path: str,
    temp_dir: str,
    logger: Logger,
    max_pages: int,
    progress_signal=None,
    page_signal=None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """
    1) Text-layer extraction (fast)
    2) Header/footer filter
    3) If mostly empty -> OCR fallback
    4) Else -> build chapters from extracted lines
    5) Cooperative cancel via cancel_check()
    """

    if cancel_check is None:
        cancel_check = lambda: False

    source_file = os.path.basename(pdf_path)
    os.makedirs(temp_dir, exist_ok=True)

    def cancelled(msg: str) -> Dict[str, Any]:
        if progress_signal:
            progress_signal.emit(msg)
        return _empty_struct(source_file)

    # --- total pages ---
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            total_pdf_pages = len(reader.pages)
    except Exception as e:
        logger.error("Не удалось прочитать PDF через PyPDF2", e)
        if progress_signal:
            progress_signal.emit(f"❌ Ошибка чтения PDF: {e}")
        return _empty_struct(source_file)

    total_pages = min(int(max_pages), int(total_pdf_pages))
    if total_pages <= 0:
        return _empty_struct(source_file)

    if cancel_check():
        return cancelled("⛔ Отменено до старта анализа")

    # --- 1) extract text lines per page ---
    pages_lines: List[list] = []

    for page_idx, lines in enumerate(extract_lines_streaming(pdf_path, max_pages=total_pages, logger=logger)):
        if cancel_check():
            return cancelled("⛔ Отмена: остановка при извлечении текстового слоя")

        pages_lines.append(lines)

        if progress_signal:
            progress_signal.emit(f"Страница {page_idx + 1}/{total_pages}: строк {len(lines)}")

        # meta for UI
        if page_signal:
            try:
                payload = {"page_number": page_idx + 1, "lines": len(lines)}
                page_signal.emit(page_idx + 1, json.dumps(payload, ensure_ascii=False))
            except Exception:
                pass

    if cancel_check():
        return cancelled("⛔ Отмена: после извлечения текстового слоя")

    # --- 2) filter headers/footers ---
    try:
        # поддержка обеих сигнатур
        try:
            pages_lines = filter_headers_footers(pages_lines, logger=logger)
        except TypeError:
            pages_lines = filter_headers_footers(pages_lines)
    except Exception as e:
        logger.error("Ошибка фильтра колонтитулов", e)

    if cancel_check():
        return cancelled("⛔ Отмена: после фильтра колонтитулов")

    # пересчёт пустых страниц ПОСЛЕ фильтра
    empty_count_after = sum(1 for p in pages_lines if not p)
    empty_ratio = empty_count_after / max(1, len(pages_lines))

    # --- 3) OCR fallback if mostly empty ---
    if empty_ratio >= 0.70:
        if progress_signal:
            progress_signal.emit("Текстового слоя почти нет → OCR fallback")

        opts = OcrOptions(
            poppler_bin=_resolve_poppler_bin(),
            dpi=300,
            lang="rus",
            grayscale=True,
            use_pdftocairo=False,
        )

        if cancel_check():
            return cancelled("⛔ Отмена: перед OCR")

        try:
            # поддержка версий с/без cancel_check
            try:
                return parse_scanned_pdf_ocr(
                    pdf_path=pdf_path,
                    total_pages=total_pages,
                    opts=opts,
                    logger=logger,
                    progress_signal=progress_signal,
                    cancel_check=cancel_check,
                )
            except TypeError:
                # legacy signature
                return parse_scanned_pdf_ocr(
                    pdf_path=pdf_path,
                    total_pages=total_pages,
                    opts=opts,
                    logger=logger,
                    progress_signal=progress_signal,
                )
        except Exception as e:
            logger.error("OCR fallback упал", e)
            if progress_signal:
                progress_signal.emit(f"❌ OCR fallback ошибка: {e}")
            return _empty_struct(source_file)

    # --- 4) build chapters normally ---
    if cancel_check():
        return cancelled("⛔ Отмена: перед сборкой структуры")

    try:
        try:
            chapters = build_chapters_from_pages(pages_lines, logger=logger)
        except TypeError:
            chapters = build_chapters_from_pages(pages_lines)
    except Exception as e:
        logger.error("Ошибка сборки глав/параграфов", e)
        if progress_signal:
            progress_signal.emit(f"❌ Ошибка сборки структуры: {e}")
        return _empty_struct(source_file)

    if cancel_check():
        return cancelled("⛔ Отмена: после сборки структуры")

    try:
        structured = build_structured_json(source_file=source_file, chapters=chapters)
    except TypeError:
        structured = build_structured_json(source_file, chapters)

    return structured
