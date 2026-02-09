import os
import json
from typing import List, Dict, Any

from pypdf import PdfReader, PdfWriter
from dedoc import DedocManager

from text_utils import normalize_text


# =========================
# КОНФИГУРАЦИЯ
# =========================

INPUT_PDF = r"C:\Users\Admin\Documents\PDF_import\5a213f4f24_literatura-9-klass-1-chast.pdf"

TEMP_PDF = r"Temp\subset.pdf"

RAW_JSON = r"Json\parsed_subset.json"
PLAIN_TEXT_JSON = r"Json\plain_text_for_llm.json"

START_PAGE = 4
END_PAGE = 10


# =========================
# PDF → SUBSET
# =========================

def extract_pages(
    input_pdf: str,
    output_pdf: str,
    start_page: int,
    end_page: int
) -> bool:
    """
    Извлекает страницы [start_page, end_page] (1-индексация),
    автоматически зажимая диапазон в пределах документа.
    """
    reader = PdfReader(input_pdf)
    writer = PdfWriter()

    total_pages = len(reader.pages)

    start = max(1, start_page)
    end = min(end_page, total_pages)

    if start > end:
        print(
            f"[WARN] Диапазон пуст: start={start_page}, "
            f"end={end_page}, pages={total_pages}"
        )
        return False

    for page_num in range(start - 1, end):
        writer.add_page(reader.pages[page_num])

    os.makedirs(os.path.dirname(output_pdf), exist_ok=True)
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

def parse_pdf_with_dedoc(pdf_path: str) -> Dict[str, Any]:
    """
    Парсит PDF через dedoc и возвращает JSON-словарь.
    """
    manager = DedocManager()
    params = {
        "language": "rus"
    }
    result = manager.parse(file_path=pdf_path, parameters=params)
    return result.to_api_schema().model_dump()


def save_json(data: Any, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] JSON сохранён: {path}")


# =========================
# DEDOC → ПЛОСКИЙ ТЕКСТ ДЛЯ LLM
# =========================

def extract_plain_text(dedoc_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Превращает dedoc-структуру в линейный список страниц с текстом.
    Формат — идеальный вход для LLM.

    [
      { "page": 4, "text": "..." },
      { "page": 5, "text": "..." }
    ]
    """
    blocks: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any]):
        raw_text = node.get("text", "")
        page = node.get("metadata", {}).get("page_id")

        if raw_text:
            text = normalize_text(raw_text)
            if text:
                blocks.append({
                    "page": page,
                    "text": text
                })

        for ch in node.get("subparagraphs", []):
            walk(ch)

    root = dedoc_json["content"]["structure"]
    walk(root)

    return blocks


# =========================
# ОСНОВНОЙ ПАЙПЛАЙН
# =========================

def run_pipeline() -> None:
    # 1. Вырезаем страницы
    ok = extract_pages(
        input_pdf=INPUT_PDF,
        output_pdf=TEMP_PDF,
        start_page=START_PAGE,
        end_page=END_PAGE
    )

    if not ok:
        return

    try:
        # 2. Парсим через dedoc
        raw_json = parse_pdf_with_dedoc(TEMP_PDF)
        save_json(raw_json, RAW_JSON)

        # 3. Готовим текст для LLM
        plain_text = extract_plain_text(raw_json)
        save_json(plain_text, PLAIN_TEXT_JSON)

        print("[OK] Текст подготовлен для передачи в LLM")

    finally:
        # 4. Удаляем временный PDF
        if os.path.exists(TEMP_PDF):
            os.remove(TEMP_PDF)
            print(f"[OK] Временный файл удалён: {TEMP_PDF}")


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    run_pipeline()
