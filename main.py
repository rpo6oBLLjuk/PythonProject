import os
import json
from typing import List, Dict, Any

from pypdf import PdfReader, PdfWriter
from dedoc import DedocManager

from text_utils import normalize_text
from chunker import TextChunker
from ollama_client import OllamaClient
from validator import JSONStructureValidator


# =========================
# КОНФИГУРАЦИЯ
# =========================

INPUT_PDF = r"C:\Users\Admin\Documents\PDF_import\5a213f4f24_literatura-9-klass-1-chast.pdf"

TEMP_PDF = r"Temp\subset.pdf"

RAW_JSON = r"Json\parsed_subset.json"
PLAIN_TEXT_JSON = r"Json\plain_text_for_llm.json"
STRUCTURED_JSON = r"Json\structured_result.json"

SCHEMA_PATH = r"schema.json"

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
    manager = DedocManager()
    params = {"language": "rus"}
    result = manager.parse(file_path=pdf_path, parameters=params)
    return result.to_api_schema().model_dump()


def save_json(data: Any, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] JSON сохранён: {path}")


# =========================
# DEDOC → ПЛОСКИЙ ТЕКСТ
# =========================

def extract_plain_text(dedoc_json: Dict[str, Any]) -> List[Dict[str, Any]]:
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
# PLAIN TEXT → LLM → JSON
# =========================

def blocks_to_text(blocks: List[Dict[str, Any]]) -> str:
    return "\n\n".join(b["text"] for b in blocks)


def build_prompt(text: str) -> str:
    return f"""
Ты преобразуешь учебный текст в строгий JSON.

Правила:
- НЕ сокращай текст
- НЕ перефразируй
- НЕ добавляй ничего от себя
- сохраняй порядок текста
- каждый логический фрагмент — block
- списки → block(kind="list")
- вопросы и задания → block(kind="questions")

Структура:
chapter → paragraph → section → block

Верни ТОЛЬКО JSON.

Текст:
{text}
""".strip()


# =========================
# ОСНОВНОЙ ПАЙПЛАЙН
# =========================

def run_pipeline() -> None:
    ok = extract_pages(
        INPUT_PDF,
        TEMP_PDF,
        START_PAGE,
        END_PAGE
    )
    if not ok:
        return

    try:
        # 1. dedoc
        raw_json = parse_pdf_with_dedoc(TEMP_PDF)
        save_json(raw_json, RAW_JSON)

        # 2. plain text
        plain_blocks = extract_plain_text(raw_json)
        save_json(plain_blocks, PLAIN_TEXT_JSON)

        # 3. чанкинг
        chunker = TextChunker(max_chars=4500, soft_limit=3500)
        chunks = chunker.chunk(plain_blocks)

        print(f"[OK] Получено чанков: {len(chunks)}")

        # 4. LLM + валидация
        llm = OllamaClient()
        validator = JSONStructureValidator(SCHEMA_PATH)

        structured_results = []

        for idx, chunk in enumerate(chunks, start=1):
            print(f"[LLM] Чанк {idx}/{len(chunks)}")

            text = blocks_to_text(chunk)
            prompt = build_prompt(text)

            response = llm.generate(prompt)

            try:
                parsed = json.loads(response)
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"❌ Некорректный JSON от LLM (чанк {idx})"
                ) from e

            errors = validator.validate(parsed)
            if errors:
                print("❌ Ошибки валидации:")
                for err in errors:
                    print(" -", err)
                raise RuntimeError(f"JSON не прошёл валидацию (чанк {idx})")

            structured_results.append(parsed)

        save_json(structured_results, STRUCTURED_JSON)
        print("[OK] Структурированный JSON готов")

    finally:
        if os.path.exists(TEMP_PDF):
            os.remove(TEMP_PDF)
            print(f"[OK] Временный файл удалён: {TEMP_PDF}")


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    run_pipeline()
