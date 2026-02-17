import os
import json
import datetime
from typing import List, Optional

from pypdf import PdfReader
from dedoc import DedocManager


# =========================================================
# CONFIG
# =========================================================

ROOT_DIR = r"C:\Users\Admin\Documents\GDrive\Мой диск\Work\Textbooks"  # папка для рекурсивного обхода
SAVE_DEDOC_JSON = False  # True если хочешь ещё сохранять dedoc-json рядом

# Ограничение для быстрой проверки текстового слоя:
# проверяем первые N страниц (обычно хватает, чтобы понять)
TEXT_LAYER_CHECK_PAGES = 5


# =========================================================
# HELPERS
# =========================================================

def choose_language_by_filename(filename: str) -> str:
    # правило: если в названии есть "английский" (любой регистр) => eng
    # иначе rus
    if "английский" in filename.lower():
        return "eng"
    return "rus"


def pdf_has_text_layer(pdf_path: str, pages_to_check: int = 5) -> bool:
    """
    Быстрая проверка: есть ли в PDF извлекаемый текст.
    Если хоть на одной из первых N страниц extract_text() вернул непустое — считаем, что слой текста есть.
    """
    try:
        reader = PdfReader(pdf_path)
        total = len(reader.pages)
        n = min(pages_to_check, total)

        for i in range(n):
            txt = reader.pages[i].extract_text() or ""
            if txt.strip():
                return True

        # Дополнительно (чуть усиление): иногда текст есть не в первых страницах.
        # Если документ короткий — проверим все.
        if total <= pages_to_check:
            return False

        return False
    except Exception:
        # Если не смогли прочитать PDF (битый/защищённый),
        # безопаснее пропустить, чтобы не тратить OCR/не падать.
        return True


def parse_pdf_ocr_only(pdf_path: str, language: str) -> dict:
    """
    Dedoc OCR-режим: принудительно считаем что текстового слоя нет.
    Это соответствует требованию "только сканы/изображения".
    """
    manager = DedocManager()
    params = {
        "pdf_with_text_layer": "false",            # ВАЖНО: принудительно OCR
        "need_pdf_table_analysis": "false",
        "need_header_footer_analysis": "false",
        "need_binarization": "false",
        "need_gost_frame_analysis": "false",
        "language": language,
        # можно добавить pages=":" при необходимости, обычно не нужно
    }
    result = manager.parse(file_path=pdf_path, parameters=params)
    return result.to_api_schema().model_dump()


def extract_plain_text_lines(dedoc_json: dict) -> List[str]:
    lines: List[str] = []

    def walk(node: dict):
        text = node.get("text")
        if isinstance(text, str) and text.strip():
            lines.append(text.strip())

        for ch in node.get("subparagraphs", []) or []:
            walk(ch)

    structure = dedoc_json.get("content", {}).get("structure")
    if isinstance(structure, dict):
        walk(structure)

    return lines


def pdf_to_txt_path(pdf_path: str) -> str:
    base, _ = os.path.splitext(pdf_path)
    return base + ".txt"


def save_text(txt_path: str, lines: List[str]) -> None:
    os.makedirs(os.path.dirname(txt_path), exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def save_json_sidecar(pdf_path: str, dedoc_json: dict) -> None:
    base, _ = os.path.splitext(pdf_path)
    json_path = base + ".dedoc.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dedoc_json, f, ensure_ascii=False, indent=2)


# =========================================================
# MAIN
# =========================================================

def run_recursive(root_dir: str):
    print(datetime.datetime.now(), f"[INFO] Scan folder: {root_dir}")

    processed = 0
    skipped_text_layer = 0
    skipped_errors = 0

    for dirpath, _, filenames in os.walk(root_dir):
        for name in filenames:
            if not name.lower().endswith(".pdf"):
                continue

            pdf_path = os.path.join(dirpath, name)

            # 2) Только документы без текстового слоя
            if pdf_has_text_layer(pdf_path, pages_to_check=TEXT_LAYER_CHECK_PAGES):
                skipped_text_layer += 1
                print(datetime.datetime.now(), f"[SKIP] Has text layer: {pdf_path}")
                continue

            lang = choose_language_by_filename(name)
            txt_path = pdf_to_txt_path(pdf_path)

            # если txt уже существует — можешь оставить/перезаписать.
            # тут перезаписываем.
            try:
                print(datetime.datetime.now(), f"[INFO] OCR parse start ({lang}): {pdf_path}")
                dedoc_json = parse_pdf_ocr_only(pdf_path, language=lang)
                lines = extract_plain_text_lines(dedoc_json)
                save_text(txt_path, lines)

                if SAVE_DEDOC_JSON:
                    save_json_sidecar(pdf_path, dedoc_json)

                processed += 1
                print(datetime.datetime.now(), f"[OK] Saved: {txt_path} (blocks={len(lines)})")

            except Exception as e:
                skipped_errors += 1
                print(datetime.datetime.now(), f"[ERR] Failed: {pdf_path}\n    {type(e).__name__}: {e}")

    print()
    print(datetime.datetime.now(), "[DONE]")
    print(f"Processed OCR PDFs: {processed}")
    print(f"Skipped (has text layer): {skipped_text_layer}")
    print(f"Skipped (errors): {skipped_errors}")


if __name__ == "__main__":
    run_recursive(ROOT_DIR)
