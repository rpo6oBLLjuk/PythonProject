# Для считывания PDF
import PyPDF2
# Для анализа структуры PDF и извлечения текста
from pdfminer.high_level import extract_pages, extract_text
from pdfminer.layout import LTTextContainer, LTChar, LTRect, LTFigure
# Для извлечения текста из таблиц в PDF
import pdfplumber
# Для извлечения изображений из PDF
from PIL import Image
from pdf2image import convert_from_path
# Для выполнения OCR, чтобы извлекать тексты из изображений
import pytesseract
# Для удаления дополнительно созданных файлов
import os
import sys
import traceback
from datetime import datetime
import time


# Создаём папки для результатов
def create_output_folders():
    """Создаёт необходимые папки для вывода результатов"""
    project_dir = os.path.dirname(os.path.abspath(__file__))

    # Основная папка для результатов
    output_dir = os.path.join(project_dir, "Output")
    os.makedirs(output_dir, exist_ok=True)

    # Подпапки
    logs_dir = os.path.join(output_dir, "Logs")
    results_dir = os.path.join(output_dir, "Results")
    temp_dir = os.path.join(output_dir, "Temp")

    for folder in [logs_dir, results_dir, temp_dir]:
        os.makedirs(folder, exist_ok=True)

    return output_dir, logs_dir, results_dir, temp_dir


# Класс для логирования
class Logger:
    def __init__(self, logs_dir):
        self.logs_dir = logs_dir
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(logs_dir, f"pdf_processing_{timestamp}.log")
        self.start_time = time.time()

    def log(self, message, level="INFO"):
        """Записывает сообщение в лог файл и выводит в консоль"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"

        # Вывод в консоль
        print(log_message)

        # Запись в файл
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + "\n")

    def log_error(self, message, exception=None):
        """Логирует ошибку с трассировкой"""
        self.log(message, "ERROR")
        if exception:
            error_details = traceback.format_exc()
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"Ошибка: {str(exception)}\n")
                f.write(f"Детали:\n{error_details}\n")

    def log_success(self, message):
        """Логирует успешное завершение"""
        self.log(message, "SUCCESS")

    def log_warning(self, message):
        """Логирует предупреждение"""
        self.log(message, "WARNING")

    def get_processing_time(self):
        """Возвращает время обработки"""
        elapsed = time.time() - self.start_time
        return f"{elapsed:.2f} секунд"


# Создаём функцию для извлечения текста
def text_extraction(element, logger):
    """Извлекает текст и его формат из элемента"""
    try:
        # Извлекаем текст из вложенного текстового элемента
        line_text = element.get_text()

        # Находим форматы текста
        line_formats = []
        for text_line in element:
            if isinstance(text_line, LTTextContainer):
                # Итеративно обходим каждый символ в строке текста
                for character in text_line:
                    if isinstance(character, LTChar):
                        # Добавляем к символу название шрифта
                        line_formats.append(character.fontname)
                        # Добавляем к символу размер шрифта
                        line_formats.append(character.size)

        # Находим уникальные размеры и названия шрифтов в строке
        format_per_line = list(set(line_formats))

        # Возвращаем кортеж с текстом в каждой строке вместе с его форматом
        return (line_text, format_per_line)
    except Exception as e:
        logger.log_error("Ошибка при извлечении текста", e)
        return ("", [])


# Создаём функцию для вырезания элементов изображений из PDF
def crop_image(element, pageObj, temp_dir, logger):
    """Вырезает изображение из PDF страницы"""
    temp_pdf_path = os.path.join(temp_dir, "cropped_image.pdf")
    try:
        # Получаем координаты для вырезания изображения из PDF
        [image_left, image_top, image_right, image_bottom] = [
            element.x0, element.y0, element.x1, element.y1
        ]
        # Обрезаем страницу по координатам
        pageObj.mediabox.lower_left = (image_left, image_bottom)
        pageObj.mediabox.upper_right = (image_right, image_top)

        # Сохраняем обрезанную страницу в новый PDF
        cropped_pdf_writer = PyPDF2.PdfWriter()
        cropped_pdf_writer.add_page(pageObj)

        with open(temp_pdf_path, 'wb') as cropped_pdf_file:
            cropped_pdf_writer.write(cropped_pdf_file)

        return temp_pdf_path
    except Exception as e:
        logger.log_error("Ошибка при обрезке изображения", e)
        return None


# Создаём функцию для преобразования PDF в изображения
def convert_to_images(input_file, temp_dir, logger):
    """Конвертирует PDF в изображение"""
    temp_image_path = os.path.join(temp_dir, "PDF_image.png")
    try:
        poppler_path = r'C:\Users\Admin\Documents\Github\PythonProject\Packages\poppler-25.12.0\Library\bin'
        images = convert_from_path(input_file, poppler_path=poppler_path)

        if images:
            image = images[0]
            image.save(temp_image_path, "PNG")
            logger.log(f"Изображение сохранено: {temp_image_path}")
            return temp_image_path
        return None
    except Exception as e:
        logger.log_error("Ошибка при конвертации PDF в изображение", e)
        return None


# Создаём функцию для считывания текста из изображений
def image_to_text(image_path, logger):
    """Извлекает текст из изображения с помощью OCR"""
    try:
        # Считываем изображение
        img = Image.open(image_path)

        # Пробуем распознать с русским языком, если не получится - без языка
        try:
            text = pytesseract.image_to_string(img, lang='rus')
        except:
            text = pytesseract.image_to_string(img)

        logger.log(f"Текст из изображения извлечен ({len(text)} символов)")
        return text
    except Exception as e:
        logger.log_error("Ошибка при распознавании текста из изображения", e)
        return ""


def extract_table(pdf_path, page_num, table_num, logger):
    """Извлекает таблицу из PDF"""
    try:
        # Открываем файл pdf
        pdf = pdfplumber.open(pdf_path)
        # Находим исследуемую страницу
        table_page = pdf.pages[page_num]
        # Извлекаем соответствующую таблицу
        tables = table_page.extract_tables()

        if tables and table_num < len(tables):
            table = tables[table_num]
            pdf.close()
            return table
        else:
            logger.log_warning(f"Таблица {table_num} не найдена на странице {page_num}")
            pdf.close()
            return None
    except Exception as e:
        logger.log_error(f"Ошибка при извлечении таблицы {table_num} со страницы {page_num}", e)
        return None


# Преобразуем таблицу в соответствующий формат
def table_converter(table, logger):
    """Преобразует таблицу в строковый формат"""
    try:
        table_string = ''
        # Итеративно обходим каждую строку в таблице
        for row_num in range(len(table)):
            row = table[row_num]
            # Удаляем разрыв строки из текста с переносом
            cleaned_row = [
                item.replace('\n', ' ') if item is not None and '\n' in item
                else '' if item is None
                else item
                for item in row
            ]
            # Преобразуем таблицу в строку
            table_string += ('|' + '|'.join(cleaned_row) + '|' + '\n')
        # Удаляем последний разрыв строки
        table_string = table_string[:-1]
        return table_string
    except Exception as e:
        logger.log_error("Ошибка при преобразовании таблицы", e)
        return ""


def save_results(text_per_page, results_dir, logger):
    """Сохраняет результаты обработки в файлы"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Файл с полными результатами
        full_results_path = os.path.join(results_dir, f"full_results_{timestamp}.txt")

        # Файл с чистыми текстами (без разметки)
        clean_text_path = os.path.join(results_dir, f"extracted_text_{timestamp}.txt")

        # Статистический файл
        stats_path = os.path.join(results_dir, f"statistics_{timestamp}.txt")

        # Сохраняем полные результаты
        with open(full_results_path, 'w', encoding='utf-8') as f:
            f.write(f"РЕЗУЛЬТАТЫ ОБРАБОТКИ PDF\n")
            f.write(f"Время обработки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Обработано страниц: {len(text_per_page)}\n")
            f.write("=" * 80 + "\n\n")

            total_text_length = 0
            total_images = 0
            total_tables = 0

            for page_key in sorted(text_per_page.keys()):
                page_data = text_per_page[page_key]
                page_text, line_format, text_from_images, text_from_tables, page_content = page_data

                page_num = page_key.replace('Page_', '')

                f.write(f"\n{'=' * 80}\n")
                f.write(f"СТРАНИЦА {int(page_num) + 1}\n")
                f.write(f"{'=' * 80}\n\n")

                # Текст страницы
                f.write("ТЕКСТ СТРАНИЦЫ:\n")
                f.write("-" * 40 + "\n")
                for text_line in page_text:
                    if text_line not in ['image', 'table']:
                        f.write(text_line)

                # Текст из изображений
                if text_from_images:
                    total_images += len(text_from_images)
                    f.write(f"\n\nТЕКСТ ИЗ ИЗОБРАЖЕНИЙ ({len(text_from_images)}):\n")
                    f.write("-" * 40 + "\n")
                    for i, img_text in enumerate(text_from_images, 1):
                        f.write(f"\nИзображение {i}:\n{img_text}\n")

                # Текст из таблиц
                if text_from_tables:
                    total_tables += len(text_from_tables)
                    f.write(f"\n\nТАБЛИЦЫ ({len(text_from_tables)}):\n")
                    f.write("-" * 40 + "\n")
                    for i, table_text in enumerate(text_from_tables, 1):
                        f.write(f"\nТаблица {i}:\n{table_text}\n")

                # Чистый текст страницы (для отдельного файла)
                clean_text = ''.join(page_content)
                total_text_length += len(clean_text)

        # Сохраняем чистый текст в отдельный файл
        with open(clean_text_path, 'w', encoding='utf-8') as f:
            for page_key in sorted(text_per_page.keys()):
                page_data = text_per_page[page_key]
                page_content = page_data[4]
                clean_text = ''.join(page_content)

                f.write(f"\n{'=' * 80}\n")
                f.write(f"СТРАНИЦА {int(page_key.replace('Page_', '')) + 1}\n")
                f.write(f"{'=' * 80}\n\n")
                f.write(clean_text)
                f.write("\n")

        # Сохраняем статистику
        with open(stats_path, 'w', encoding='utf-8') as f:
            f.write("СТАТИСТИКА ОБРАБОТКИ PDF\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Общее количество страниц: {len(text_per_page)}\n")
            f.write(f"Общий объем текста: {total_text_length} символов\n")
            f.write(f"Извлечено изображений с текстом: {total_images}\n")
            f.write(f"Извлечено таблиц: {total_tables}\n")
            f.write(f"Время обработки: {logger.get_processing_time()}\n")
            f.write(f"Дата обработки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        logger.log_success(f"Результаты сохранены:")
        logger.log(f"  - Полные результаты: {full_results_path}")
        logger.log(f"  - Извлеченный текст: {clean_text_path}")
        logger.log(f"  - Статистика: {stats_path}")

        return full_results_path, clean_text_path, stats_path

    except Exception as e:
        logger.log_error("Ошибка при сохранении результатов", e)
        return None, None, None


def process_pdf(pdf_path, max_pages=None):
    """Основная функция обработки PDF"""

    # Создаем папки для результатов
    output_dir, logs_dir, results_dir, temp_dir = create_output_folders()

    # Инициализируем логгер
    logger = Logger(logs_dir)

    logger.log("=" * 80)
    logger.log("НАЧАЛО ОБРАБОТКИ PDF")
    logger.log(f"PDF файл: {pdf_path}")
    logger.log(f"Папка для результатов: {output_dir}")
    logger.log("=" * 80)

    if not os.path.exists(pdf_path):
        logger.log_error(f"Файл не найден: {pdf_path}")
        return

    text_per_page = {}

    try:
        # Создаём объект файла PDF
        pdfFileObj = open(pdf_path, 'rb')
        # Создаём объект считывателя PDF
        pdfReaded = PyPDF2.PdfReader(pdfFileObj)

        logger.log(f"Открыт PDF файл. Всего страниц: {len(pdfReaded.pages)}")

        # Извлекаем страницы из PDF
        all_pages = list(extract_pages(pdf_path))

        if max_pages:
            pages_to_process = min(max_pages, len(all_pages))
        else:
            pages_to_process = len(all_pages)

        logger.log(f"Будет обработано страниц: {pages_to_process}")

        # Извлекаем страницы из PDF
        for pagenum, page in enumerate(all_pages[:pages_to_process]):
            logger.log(f"\nОбработка страницы {pagenum + 1}/{pages_to_process}...")

            try:
                # Инициализируем переменные для страницы
                pageObj = pdfReaded.pages[pagenum]
                page_text = []
                line_format = []
                text_from_images = []
                text_from_tables = []
                page_content = []

                # Инициализируем количество исследованных таблиц
                table_num = 0
                first_element = True
                table_extraction_flag = False

                # Открываем файл pdf для извлечения таблиц
                pdf = pdfplumber.open(pdf_path)
                page_tables = pdf.pages[pagenum]
                tables = page_tables.find_tables()
                pdf.close()

                # Находим все элементы
                if hasattr(page, '_objs'):
                    page_elements = [(element.y1, element) for element in page._objs]
                else:
                    page_elements = []
                    for element in page:
                        if hasattr(element, 'y1'):
                            page_elements.append((element.y1, element))

                # Сортируем элементы
                page_elements.sort(key=lambda a: a[0], reverse=True)

                # Обрабатываем элементы страницы
                elements_processed = 0
                images_processed = 0
                tables_processed = 0

                for i, component in enumerate(page_elements):
                    element = component[1]

                    # Проверяем, является ли элемент текстовым
                    if isinstance(element, LTTextContainer):
                        if not table_extraction_flag:
                            (line_text, format_per_line) = text_extraction(element, logger)
                            if line_text.strip():
                                page_text.append(line_text)
                                line_format.append(format_per_line)
                                page_content.append(line_text)
                                elements_processed += 1

                    # Проверяем элементы на наличие изображений
                    elif isinstance(element, LTFigure):
                        try:
                            # Вырезаем изображение из PDF
                            cropped_pdf = crop_image(element, pageObj, temp_dir, logger)
                            if cropped_pdf:
                                # Преобразуем в изображение
                                image_file = convert_to_images(cropped_pdf, temp_dir, logger)
                                if image_file:
                                    # Извлекаем текст
                                    image_text = image_to_text(image_file, logger)
                                    if image_text.strip():
                                        text_from_images.append(image_text)
                                        page_content.append(f"\n[ТЕКСТ ИЗ ИЗОБРАЖЕНИЯ]:\n{image_text}\n")
                                        page_text.append('image')
                                        line_format.append('image')
                                        images_processed += 1

                            # Удаляем временные файлы
                            for temp_file in [cropped_pdf, image_file]:
                                if temp_file and os.path.exists(temp_file):
                                    os.remove(temp_file)

                        except Exception as e:
                            logger.log_error(f"Ошибка при обработке изображения на странице {pagenum}", e)
                            continue

                    # Проверяем элементы на наличие таблиц
                    elif isinstance(element, LTRect):
                        if first_element and (table_num + 1) <= len(tables):
                            try:
                                table = extract_table(pdf_path, pagenum, table_num, logger)
                                if table:
                                    table_string = table_converter(table, logger)
                                    text_from_tables.append(table_string)
                                    page_content.append(f"\n[ТАБЛИЦА]:\n{table_string}\n")
                                    table_extraction_flag = True
                                    first_element = False
                                    page_text.append('table')
                                    line_format.append('table')
                                    tables_processed += 1
                            except Exception as e:
                                logger.log_error(f"Ошибка при обработке таблицы на странице {pagenum}", e)

                        # Сброс флага таблицы
                        if i < len(page_elements) - 1 and not isinstance(page_elements[i + 1][1], LTRect):
                            table_extraction_flag = False
                            first_element = True
                            table_num += 1

                # Сохраняем результаты страницы
                dctkey = 'Page_' + str(pagenum)
                text_per_page[dctkey] = [page_text, line_format, text_from_images, text_from_tables, page_content]

                logger.log(f"  Страница {pagenum + 1} обработана:")
                logger.log(f"    - Текстовых элементов: {elements_processed}")
                logger.log(f"    - Изображений обработано: {images_processed}")
                logger.log(f"    - Таблиц обработано: {tables_processed}")
                logger.log(f"    - Всего символов: {len(''.join(page_content))}")

            except Exception as e:
                logger.log_error(f"Критическая ошибка при обработке страницы {pagenum + 1}", e)
                continue

        # Закрываем объект файла pdf
        pdfFileObj.close()

        # Сохраняем результаты
        if text_per_page:
            save_results(text_per_page, results_dir, logger)
            logger.log_success(f"Обработка завершена успешно!")
            logger.log(f"Общее время обработки: {logger.get_processing_time()}")
        else:
            logger.log_warning("Обработка завершена, но результаты не получены")

    except Exception as e:
        logger.log_error("Критическая ошибка при обработке PDF", e)

    finally:
        # Очищаем временные файлы
        temp_files = ['cropped_image.pdf', 'PDF_image.png']
        for temp_file in temp_files:
            temp_path = os.path.join(temp_dir, temp_file)
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    logger.log(f"Удален временный файл: {temp_file}")
                except:
                    pass

        logger.log("=" * 80)
        logger.log("ОБРАБОТКА ЗАВЕРШЕНА")
        logger.log("=" * 80)

        # Выводим путь к лог файлу
        print(f"\n{'=' * 80}")
        print(f"Логи сохранены в: {logger.log_file}")
        print(f"Результаты в папке: {results_dir}")
        print(f"{'=' * 80}")


# Основная функция
def main():
    # Путь к PDF файлу
    pdf_path = 'C:/Users/Admin/Documents/PDF_import/Azbuka_1_kl_1_ch_Goretskiy_compressed.pdf'

    # Максимальное количество страниц для обработки (None = все страницы)
    max_pages_to_process = 12  # Для теста обрабатываем 3 страницы

    # Запускаем обработку
    process_pdf(pdf_path, max_pages_to_process)


# Точка входа
if __name__ == "__main__":
    main()