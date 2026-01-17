import os
import json
from pypdf import PdfReader, PdfWriter
from dedoc import DedocManager

from semantic_builder import build_semantic_hierarchy


# =========================
# КОНФИГУРАЦИЯ
# =========================

INPUT_PDF = r"C:\Users\Admin\Documents\PDF_import\5a213f4f24_literatura-9-klass-1-chast.pdf"

TEMP_PDF = "Temp\subset.pdf"

RAW_JSON = "Json\parsed_subset.json"
SEMANTIC_JSON = "Json\semantic_hierarchy.json"

START_PAGE = 0
END_PAGE = 420


# =========================
# PDF → SUBSET
# =========================

from pypdf import PdfReader, PdfWriter


def extract_pages(
    input_pdf: str,
    output_pdf: str,
    start_page: int,
    end_page: int
):
    """
    Извлекает страницы [start_page, end_page] (1-индексация),
    автоматически зажимая диапазон в пределах документа.
    """

    reader = PdfReader(input_pdf)
    writer = PdfWriter()

    total_pages = len(reader.pages)

    # --- нормализация диапазона ---
    start = max(1, start_page)
    end = min(end_page, total_pages)

    if start > end:
        print(
            f"[WARN] Диапазон пуст: start={start_page}, "
            f"end={end_page}, pages={total_pages}"
        )
        return False

    # --- извлечение ---
    for page_num in range(start - 1, end):
        writer.add_page(reader.pages[page_num])

    with open(output_pdf, "wb") as f:
        writer.write(f)

    print(
        f"[OK] Извлечены страницы {start}–{end} "
        f"(из {total_pages}) → {output_pdf}"
    )

    return True



# =========================
# SUBSET → DEDOC JSON
# =========================

def parse_pdf_with_dedoc(pdf_path: str) -> dict:
    """
    Парсит PDF через dedoc и возвращает JSON-словарь.
    """
    manager = DedocManager()

    params = {
        "language": "rus"
    }

    result = manager.parse(file_path=pdf_path, parameters=params)
    return result.to_api_schema().model_dump()


def save_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[OK] JSON сохранён: {path}")


# =========================
# ОСНОВНОЙ ПАЙПЛАЙН
# =========================

def run_pipeline() -> None:
    # 1. Вырезаем страницы
    extract_pages(
        input_pdf=INPUT_PDF,
        output_pdf=TEMP_PDF,
        start_page=START_PAGE,
        end_page=END_PAGE
    )

    try:
        # 2. Парсим через dedoc
        raw_json = parse_pdf_with_dedoc(TEMP_PDF)
        save_json(raw_json, RAW_JSON)

        # 3. Строим семантическую структуру
        semantic = build_semantic_hierarchy(raw_json)
        save_json(semantic, SEMANTIC_JSON)

    finally:
        # 4. Убираем временный PDF
        if os.path.exists(TEMP_PDF):
            os.remove(TEMP_PDF)
            print(f"[OK] Временный файл удалён: {TEMP_PDF}")


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    run_pipeline()
