import os
from pypdf import PdfReader, PdfWriter
from dedoc import DedocManager
import json

# исходный PDF и коэффициенты
INPUT_PDF = r"C:\Users\Admin\Documents\PDF_import\Azbuka_1_kl_1_ch_Goretskiy_compressed.pdf"
TEMP_PDF = "subset.pdf"
OUTPUT_JSON = "parsed_subset.json"

# указываем номера страниц, которые нужны
# ВАЖНО: pypdf использует 0-индексацию, поэтому -1
start_page = 4
end_page = 5

def extract_pages(input_pdf: str, output_pdf: str, start: int, end: int):
    """
    Извлечь страницы [start, end] (1-индексация для пользователя)
    """
    reader = PdfReader(input_pdf)
    writer = PdfWriter()

    # конвертируем в 0-индексацию
    start_index = start - 1
    end_index = end - 1

    for i in range(start_index, end_index + 1):
        if i < len(reader.pages):
            writer.add_page(reader.pages[i])
        else:
            print(f"Страница {i+1} отсутствует в документе")

    with open(output_pdf, "wb") as f:
        writer.write(f)

    print(f"Временный PDF с {start}–{end} сохранён как {output_pdf}")

# сначала делаем "урезанный" PDF с нужными страницами
extract_pages(INPUT_PDF, TEMP_PDF, start_page, end_page)

# парсим получившийся PDF
manager = DedocManager()

params = {
    "language": "rus"
}

result = manager.parse(file_path=TEMP_PDF, parameters=params)


# приводим к словарю для JSON
json_data = result.to_api_schema().model_dump()

# сохраняем JSON
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(json_data, f, ensure_ascii=False, indent=2)

print(f"Парсинг завершён. JSON в {OUTPUT_JSON}")

# очищаем временный PDF (если не нужен)
os.remove(TEMP_PDF)
