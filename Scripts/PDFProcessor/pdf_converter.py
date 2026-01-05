import os
import PyPDF2
import pdfplumber
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar, LTRect, LTFigure
from PIL import Image
from pdf2image import convert_from_path
import pytesseract

from Scripts.Utils.logger import Logger
from PySide6.QtCore import QThread, Signal

POPPLER_PATH = r'C:\Users\Admin\Documents\Github\PythonProject\Packages\poppler-25.12.0\Library\bin'

class PDFConverterThread(QThread):
    progress = Signal(str)        # Логи и статус по ходу
    page_ready = Signal(int, list)  # Страница готова
    finished_conversion = Signal(dict)  # Все результаты

    def __init__(self, pdf_path, temp_dir, max_pages):
        super().__init__()
        self.pdf_path = pdf_path
        self.temp_dir = temp_dir
        self.max_pages = max_pages
        self.logger = Logger(console=False)

    def run(self):
        self.logger.info("Запуск конвертации в отдельном потоке")
        try:
            result = convert_pdf_to_text(self.pdf_path, self.temp_dir, self.logger, self.max_pages, self.progress, self.page_ready)
            self.finished_conversion.emit(result)
        except Exception as e:
            self.logger.error("Ошибка в потоке", e)
            self.finished_conversion.emit({})

def text_extraction(element, logger):
    try:
        text = element.get_text()
        formats = []
        for line in element:
            if isinstance(line, LTTextContainer):
                for char in line:
                    if isinstance(char, LTChar):
                        formats.append((char.fontname, char.size))
        return text, list(set(formats))
    except Exception as e:
        logger.error("Ошибка извлечения текста", e)
        return "", []

def crop_image(element, pageObj, temp_dir, logger):
    try:
        path = os.path.join(temp_dir, "crop.pdf")
        pageObj.mediabox.lower_left = (element.x0, element.y0)
        pageObj.mediabox.upper_right = (element.x1, element.y1)

        writer = PyPDF2.PdfWriter()
        writer.add_page(pageObj)
        with open(path, "wb") as f:
            writer.write(f)
        return path
    except Exception as e:
        logger.error("Ошибка обрезки изображения", e)
        return None

def pdf_to_image(pdf_path, temp_dir, logger):
    try:
        images = convert_from_path(pdf_path, poppler_path=POPPLER_PATH)
        if images:
            img_path = os.path.join(temp_dir, "image.png")
            images[0].save(img_path)
            return img_path
    except Exception as e:
        logger.error("Ошибка конвертации PDF в изображение", e)
    return None

def image_to_text(image_path, logger):
    try:
        img = Image.open(image_path)
        try:
            return pytesseract.image_to_string(img, lang="rus")
        except:
            return pytesseract.image_to_string(img)
    except Exception as e:
        logger.error("Ошибка OCR", e)
        return ""

def extract_table(pdf_path, page_num, table_num, logger):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            tables = pdf.pages[page_num].extract_tables()
            if table_num < len(tables):
                return tables[table_num]
    except Exception as e:
        logger.error("Ошибка извлечения таблицы", e)
    return None

def table_to_string(table):
    return "\n".join(
        "|" + "|".join(cell or "" for cell in row) + "|" for row in table
    )

def convert_pdf_to_text(pdf_path, temp_dir, logger, max_pages=None, progress_signal=None, page_signal=None):
    text_per_page = {}

    reader = PyPDF2.PdfReader(open(pdf_path, "rb"))
    pages = list(extract_pages(pdf_path))
    pages = pages[:max_pages] if max_pages else pages

    for idx, page in enumerate(pages):
        logger.info(f"Обработка страницы {idx + 1}")
        if progress_signal:
            progress_signal.emit(f"Обработка страницы {idx + 1}")

        pageObj = reader.pages[idx]
        page_text, formats = [], []
        images_text, tables_text = [], []
        page_content = []

        elements = sorted(
            [(el.y1, el) for el in page if hasattr(el, "y1")],
            key=lambda x: x[0], reverse=True
        )

        table_idx = 0

        for _, el in elements:
            if isinstance(el, LTTextContainer):
                text, fmt = text_extraction(el, logger)
                if text.strip():
                    page_text.append(text)
                    formats.append(fmt)
                    page_content.append(text)

            elif isinstance(el, LTFigure):
                cropped = crop_image(el, pageObj, temp_dir, logger)
                if cropped:
                    img = pdf_to_image(cropped, temp_dir, logger)
                    if img:
                        text = image_to_text(img, logger)
                        if text.strip():
                            images_text.append(text)
                            page_content.append(text)

            elif isinstance(el, LTRect):
                table = extract_table(pdf_path, idx, table_idx, logger)
                if table:
                    table_text = table_to_string(table)
                    tables_text.append(table_text)
                    page_content.append(table_text)
                    table_idx += 1

        text_per_page[f"Page_{idx}"] = [
            page_text,
            formats,
            images_text,
            tables_text,
            page_content,
        ]

        if page_signal:
            page_signal.emit(idx + 1, page_content)

    return text_per_page