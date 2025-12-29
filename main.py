# Для считывания PDF
import PyPDF2
# Для анализа структуры PDF и извлечения текста
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar, LTRect, LTFigure
# Для извлечения текста из таблиц в PDF
import pdfplumber
# Для извлечения изображений из PDF
from PIL import Image
from pdf2image import convert_from_path
# Для выполнения OCR
import pytesseract
# Системные
import os
import traceback

# Внутренние модули
from Scripts.Utils.logger import Logger
from Scripts.Utils.results import save_results


# ================================
# Создание выходных папок
# ================================

def create_output_folders():
    project_dir = os.path.dirname(os.path.abspath(__file__))

    output_dir = os.path.join(project_dir, "Output")
    logs_dir = os.path.join(output_dir, "Logs")
    results_dir = os.path.join(output_dir, "Results")
    temp_dir = os.path.join(output_dir, "Temp")

    for folder in (output_dir, logs_dir, results_dir, temp_dir):
        os.makedirs(folder, exist_ok=True)

    return logs_dir, results_dir, temp_dir


# ================================
# Вспомогательные функции
# ================================

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
        poppler_path = r'C:\Users\Admin\Documents\Github\PythonProject\Packages\poppler-25.12.0\Library\bin'
        images = convert_from_path(pdf_path, poppler_path=poppler_path)
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
    rows = []
    for row in table:
        rows.append("|" + "|".join(cell or "" for cell in row) + "|")
    return "\n".join(rows)


# ================================
# Основная логика
# ================================

def process_pdf(pdf_path, max_pages=None, verbose=False):
    logs_dir, results_dir, temp_dir = create_output_folders()
    logger = Logger(logs_dir, console=verbose)

    logger.info("Начало обработки PDF")

    text_per_page = {}

    try:
        reader = PyPDF2.PdfReader(open(pdf_path, "rb"))
        pages = list(extract_pages(pdf_path))
        pages = pages[:max_pages] if max_pages else pages

        for idx, page in enumerate(pages):
            logger.info(f"Обработка страницы {idx + 1}")

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
                        tables_text.append(table_to_string(table))
                        page_content.append(table_to_string(table))
                        table_idx += 1

            text_per_page[f"Page_{idx}"] = [
                page_text,
                formats,
                images_text,
                tables_text,
                page_content,
            ]

        results = save_results(text_per_page, results_dir)

        print("\nРезультаты обработки:")
        for k, v in results.items():
            print(f"{k}: {v}")

        logger.success("Обработка завершена")

    except Exception as e:
        logger.error("Критическая ошибка", e)

    finally:
        logger.info("Завершение работы")


# ================================
# Точка входа
# ================================

def main():
    pdf_path = "C:/Users/Admin/Documents/PDF_import/Azbuka_1_kl_1_ch_Goretskiy_compressed.pdf"
    process_pdf(pdf_path, max_pages=12, verbose=True)


if __name__ == "__main__":
    main()
