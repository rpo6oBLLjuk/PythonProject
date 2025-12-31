import os
import PyPDF2
import pdfplumber
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar, LTRect, LTFigure
from PIL import Image
from pdf2image import convert_from_path
import pytesseract
import json
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict, Any
import re

from Scripts.Utils.logger import Logger
from PySide6.QtCore import QThread, Signal

POPPLER_PATH = r'Packages\poppler-25.12.0\Library\bin'


@dataclass
class TextElementData:
    """Упрощенная структура для передачи через сигналы"""
    text: str
    element_type: str
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    is_bold: bool = False
    is_italic: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "type": self.element_type,
            "font_name": self.font_name,
            "font_size": self.font_size,
            "is_bold": self.is_bold,
            "is_italic": self.is_italic
        }


class PDFConverterWithStructureThread(QThread):
    progress = Signal(str)  # Статус
    page_ready = Signal(int, str)  # Номер страницы и JSON данные
    finished_conversion = Signal(str)  # Все результаты в JSON

    def __init__(self, pdf_path, temp_dir, max_pages):
        super().__init__()
        self.pdf_path = pdf_path
        self.temp_dir = temp_dir
        self.max_pages = max_pages
        self.logger = Logger(console=False)

    def run(self):
        self.logger.info("Запуск конвертации с сохранением структуры")
        try:
            result = convert_pdf_to_text_with_structure(
                self.pdf_path, self.temp_dir, self.logger,
                self.max_pages, self.progress, self.page_ready
            )
            # Сериализуем результат в JSON
            result_json = json.dumps(result, ensure_ascii=False)
            self.progress.emit("Конвертация завершена")
            self.finished_conversion.emit(result_json)
        except Exception as e:
            self.logger.error("Ошибка в потоке", e)
            self.progress.emit(f"Ошибка: {str(e)}")
            self.finished_conversion.emit("{}")


def text_extraction_with_styles(element, logger):
    """Извлечение текста со стилями"""
    try:
        text = element.get_text().strip()
        if not text:
            return []

        elements_data = []

        for text_line in element:
            if isinstance(text_line, LTTextContainer):
                line_text = ""
                current_font = None
                current_size = None
                is_bold = False
                is_italic = False

                for char in text_line:
                    if isinstance(char, LTChar):
                        if line_text and (char.fontname != current_font or char.size != current_size):
                            if line_text.strip():
                                # Определяем стили
                                if current_font:
                                    is_bold = "bold" in current_font.lower() or "black" in current_font.lower()
                                    is_italic = "italic" in current_font.lower() or "oblique" in current_font.lower()

                                elem = TextElementData(
                                    text=line_text,
                                    element_type="regular",
                                    font_name=current_font,
                                    font_size=current_size,
                                    is_bold=is_bold,
                                    is_italic=is_italic
                                )
                                elements_data.append(elem)

                            line_text = char.get_text()
                            current_font = char.fontname
                            current_size = char.size
                        else:
                            line_text += char.get_text()
                            if not current_font:
                                current_font = char.fontname
                                current_size = char.size

                if line_text.strip():
                    if current_font:
                        is_bold = "bold" in current_font.lower() or "black" in current_font.lower()
                        is_italic = "italic" in current_font.lower() or "oblique" in current_font.lower()

                    elem = TextElementData(
                        text=line_text,
                        element_type="regular",
                        font_name=current_font,
                        font_size=current_size,
                        is_bold=is_bold,
                        is_italic=is_italic
                    )
                    elements_data.append(elem)

        return elements_data
    except Exception as e:
        logger.error("Ошибка извлечения текста со стилями", e)
        return []


def crop_image(element, pageObj, temp_dir, logger):
    try:
        path = os.path.join(temp_dir, f"crop_{hash(element)}.pdf")
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
            img_path = os.path.join(temp_dir, f"image_{hash(pdf_path)}.png")
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
    if not table:
        return ""
    return "\n".join(
        "|" + "|".join(str(cell or "") for cell in row) + "|" for row in table
    )


def classify_and_group_text(elements: List[TextElementData], logger):
    """Классификация и группировка текста"""
    if not elements:
        return []

    # Анализ размеров шрифтов
    font_sizes = [e.font_size for e in elements if e.font_size]
    if font_sizes:
        avg_size = sum(font_sizes) / len(font_sizes)
    else:
        avg_size = 12

    # Классификация
    for element in elements:
        elem_type = "regular"

        # Заголовки по размеру шрифта
        if element.font_size and element.font_size > avg_size * 1.3:
            elem_type = "header"
        elif element.font_size and element.font_size > avg_size * 1.1:
            elem_type = "subheader"

        # Номера задач и варианты ответов
        elif re.match(r'^\d+[\.\)]\s*', element.text.strip()):
            elem_type = "task_number"
        elif re.match(r'^[A-Da-d][\.\)]\s*', element.text.strip()):
            elem_type = "answer_option"

        # Жирный текст
        elif element.is_bold and element.font_size and element.font_size >= avg_size:
            elem_type = "bold_text"

        element.element_type = elem_type

    # Группировка по абзацам
    return group_text_elements(elements, logger)


def group_text_elements(elements: List[TextElementData], logger):
    """Группировка элементов в абзацы"""
    if not elements:
        return []

    grouped = []
    current_group = []
    current_font = None
    current_size = None

    for element in elements:
        # Элементы, которые не группируются
        if element.element_type in ["header", "subheader", "task_number", "answer_option", "table", "image_text"]:
            # Сохраняем предыдущую группу
            if current_group:
                paragraph_text = "".join([e.text for e in current_group])
                paragraph_elem = TextElementData(
                    text=paragraph_text,
                    element_type="paragraph",
                    font_name=current_font,
                    font_size=current_size
                )
                grouped.append(paragraph_elem)
                current_group = []

            grouped.append(element)
            current_font = None
            current_size = None

        else:
            if not current_group:
                current_font = element.font_name
                current_size = element.font_size
            current_group.append(element)

    # Обработка последней группы
    if current_group:
        paragraph_text = "".join([e.text for e in current_group])
        paragraph_elem = TextElementData(
            text=paragraph_text,
            element_type="paragraph",
            font_name=current_font,
            font_size=current_size
        )
        grouped.append(paragraph_elem)

    return grouped


def convert_pdf_to_text_with_structure(pdf_path, temp_dir, logger, max_pages=None, progress_signal=None,
                                       page_signal=None):
    """Конвертация PDF в текст с сохранением структуры"""
    all_pages_data = {}

    # Открываем PDF для чтения
    reader = PyPDF2.PdfReader(open(pdf_path, "rb"))

    # Получаем страницы через pdfminer
    pages = list(extract_pages(pdf_path))
    if max_pages:
        pages = pages[:max_pages]

    total_pages = len(pages)

    for page_idx, page_layout in enumerate(pages):
        page_num = page_idx + 1

        if progress_signal:
            progress_signal.emit(f"Обработка страницы {page_num}/{total_pages}")

        pageObj = reader.pages[page_idx]
        page_elements = []

        # Сортируем элементы по вертикальной позиции (сверху вниз)
        elements = []
        for element in page_layout:
            if hasattr(element, 'y1'):
                elements.append((element.y1, element))

        elements.sort(key=lambda x: x[0], reverse=True)  # Сверху вниз

        table_idx = 0

        for _, element in elements:
            if isinstance(element, LTTextContainer):
                # Извлекаем текст со стилями
                text_elements = text_extraction_with_styles(element, logger)
                if text_elements:
                    page_elements.extend(text_elements)

            elif isinstance(element, LTFigure):
                # Обработка изображений
                cropped_pdf = crop_image(element, pageObj, temp_dir, logger)
                if cropped_pdf:
                    image_path = pdf_to_image(cropped_pdf, temp_dir, logger)
                    if image_path:
                        text = image_to_text(image_path, logger)
                        if text.strip():
                            img_element = TextElementData(
                                text=text.strip(),
                                element_type="image_text"
                            )
                            page_elements.append(img_element)

            elif isinstance(element, LTRect):
                # Обработка таблиц
                table = extract_table(pdf_path, page_idx, table_idx, logger)
                if table:
                    table_text = table_to_string(table)
                    table_element = TextElementData(
                        text=table_text,
                        element_type="table"
                    )
                    page_elements.append(table_element)
                    table_idx += 1

        # Классифицируем и группируем элементы
        if page_elements:
            classified_elements = classify_and_group_text(page_elements, logger)
        else:
            classified_elements = []

        # Формируем данные страницы
        page_data = {
            "page_number": page_num,
            "elements": [elem.to_dict() for elem in classified_elements]
        }

        all_pages_data[f"page_{page_num}"] = page_data

        # Отправляем данные страницы
        if page_signal:
            page_json = json.dumps(page_data, ensure_ascii=False)
            page_signal.emit(page_num, page_json)

    return all_pages_data