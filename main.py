import os
import json
import datetime

from pypdf import PdfReader, PdfWriter
from dedoc import DedocManager

from chunker import TextChunker
from gemini_client import GeminiClient
from ollama_client import OllamaClient
from openai_client import OpenAIClient
from safe_json_loads import safe_json_loads
from validator import JsonValidator


# =========================================================
# PIPELINE FLAGS
# =========================================================

PIPELINE = {
    "extract_pdf": False,
    "dedoc_parse": False,
    "extract_plain_text": False,
    "llm_structure": True,
    "validate_schema": True,
    "clean_text": False,
}


# =========================================================
# LLM CLIENT
# =========================================================

structure_llm = GeminiClient()
cleaner_llm = OllamaClient()

# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_PDF = r"C:\Users\Admin\Downloads\1726658755_ladyzhenskaia_t__russki_iazyk_5_klass_4.pdf"

TEMP_PDF = os.path.join(BASE_DIR, "Temp", "subset.pdf")

RAW_DEDOC_JSON = os.path.join(BASE_DIR, "Json", "parsed_subset.json")
PLAIN_JSON = os.path.join(BASE_DIR, "Json", "plain_text_for_llm.json")
RAW_LLM_JSON = os.path.join(BASE_DIR, "Json", "raw_llm_output.json")
STRUCTURED_JSON = os.path.join(BASE_DIR, "Json", "final_chapter.json")
CLEAN_JSON = os.path.join(BASE_DIR, "Json", "final_chapter_clean.json")

SCHEMA_PATH = os.path.join(BASE_DIR, "schemas", "schema.json")


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
Ты — система логической структуризации учебного или методического текста.

Тебе передаётся большой фрагмент документа.
Это может быть часть книги, учебника, методички или конспекта.

Твоя задача — автоматически восстановить логическую структуру документа
и вернуть РОВНО ОДИН JSON-объект.

СТРОГАЯ JSON-СТРУКТУРА

{
    "type": "chapter",
    "title": string | null,
    "children": [
        {
        "type": "paragraph",
        "title": string | null,
        "children": [
            {
            "type": "section",
            "title": string | null,
            "section_type": "text | exercise | task | rule | definition | list | example | note",
            "text": string | null
            }
          ]
        }
      ]
},
{
    "type": "chapter",
    "title": string | null,
    "children": [
        {
        "type": "paragraph",
        "title": string | null,
        "children": [
            {
            "type": "section",
            "title": string | null,
            "section_type": "text | exercise | task | rule | definition | list | example | note",
            "text": string | null
            }
          ]
        }
      ]
}

ОБЩИЕ ПРАВИЛА

Никаких комментариев.

Никакого markdown.

Никаких пояснений.

Только валидный JSON.

Ответ должен начинаться с "{" и заканчиваться "}".

НЕ ПРИДУМЫВАЙ И НЕ ДОПИСЫВАЙ ТЕКСТ.

ЗАПРЕЩЕНО ПЕРЕФОРМУЛИРОВАТЬ ЗАГОЛОВКИ.

ЛОГИКА УРОВНЕЙ

CHAPTER
— Самый верхний визуальный заголовок.
— Берётся ДОСЛОВНО из текста.
— Если явного заголовка нет → null.

PARAGRAPH
— Подраздел главы.
— Берётся ДОСЛОВНО из текста.
— Если подзаголовка нет → null.

SECTION
— Минимальная логическая единица внутри paragraph.
— Каждый смысловой блок оформляется как section.

СТРОГОЕ ПРАВИЛО TITLE

"title" может быть ТОЛЬКО:

дословной строкой из входного текста

полностью совпадающей с исходным фрагментом

Запрещено:

сокращать

обобщать

улучшать формулировку

давать смысловое название

придумывать краткий заголовок

интерпретировать содержание

Если отдельного заголовка в тексте нет →
"title": null

Номер задания (например "2.") не превращается в новый заголовок.
Он включается в title только если стоит как самостоятельная строка.

РАЗГРАНИЧЕНИЕ title И text

Если встречается:

Задание с номером

Если строка содержит формулировку задания
(например: "2. Прочитайте текст и определите его тему.")

→ Вся эта строка целиком идёт в "title".
→ Всё, что следует после неё и относится к этому заданию, идёт в "text".

Если задание не имеет дополнительного текста
→ "text": null

Список

Если перед списком есть заголовок
→ он идёт в "title".
→ элементы списка — в "text".
→ элементы разделяются переносами строки "\n".

Если список без заголовка
→ "title": null
→ элементы списка — в "text".

Определение

Если есть строка вида:
"Транскрипция — это ..."

→ термин до тире — в "title".
→ текст после тире — в "text".

Правило

Если есть явный заголовок правила
→ он идёт в "title".
→ формулировка правила — в "text".

Если заголовка нет
→ "title": null
→ правило целиком в "text".

Обычный текст

Если перед текстом нет отдельного заголовка
→ "title": null
→ весь текст в "text".

Запрещено создавать смысловые заголовки вроде:
"Назначение языка"
"Введение"
"Информационный блок"

Если такого текста нет во входе — такого title быть не должно.

ОПРЕДЕЛЕНИЕ section_type

Используй только:

text
exercise
task
rule
definition
list
example
note

Если тип невозможно определить — используй "text".

СТРУКТУРНЫЕ ПРАВИЛА

Не дроби текст на отдельные предложения.

Объединяй логически связанный текст в один section.

Разделяй section только если меняется тип содержимого.

Внутри text допускаются абзацы через "\n\n".

Не сокращай текст.

Не перефразируй текст.

Не добавляй ничего от себя.

ОПРЕДЕЛЕНИЕ УРОВНЯ CHAPTER

Если строка:

написана полностью ЗАГЛАВНЫМИ буквами

не содержит номера параграфа (§)

визуально выделена как крупный заголовок

не является частью задания

ТО ЭТО ОБЯЗАТЕЛЬНО "type": "chapter".

Такая строка не может быть paragraph.

Если во входном фрагменте встречается новый заголовок уровня chapter —
нужно закрыть предыдущую главу и начать новую.

ЗАПРЕЩЕНО

❌ создавать несколько chapter
❌ создавать document
❌ использовать другие поля
❌ добавлять новые типы section_type
❌ возвращать несколько JSON подряд
❌ придумывать заголовки

Верни ТОЛЬКО один валидный JSON.
""".strip()




# =========================================================
# PDF HELPERS
# =========================================================

def extract_pages(start: int, end: int):
    reader = PdfReader(INPUT_PDF)
    writer = PdfWriter()

    for i in range(start - 1, end):
        writer.add_page(reader.pages[i])

    os.makedirs(os.path.dirname(TEMP_PDF), exist_ok=True)

    with open(TEMP_PDF, "wb") as f:
        writer.write(f)


def parse_pdf():
    manager = DedocManager()
    params = {
        "language": "rus",
        "pdf_with_text_layer": "true",
        "need_pdf_table_analysis": "false",
        "need_header_footer_analysis": "false"
    }

    result = manager.parse(file_path=TEMP_PDF, parameters=params)
    return result.to_api_schema().model_dump()


def extract_plain_blocks(dedoc_json):
    blocks = []

    def walk(node):
        text = node.get("text")
        if text:
            blocks.append({"text": text})
        for ch in node.get("subparagraphs", []):
            walk(ch)

    walk(dedoc_json["content"]["structure"])
    return blocks


# =========================================================
# MAIN PIPELINE
# =========================================================

def run_pipeline():

    # ===============================
    # STEP 1 — PDF
    # ===============================

    if PIPELINE["extract_pdf"]:
        print(datetime.datetime.now(), "[INFO] Extract PDF Start")
        extract_pages(4, 100)
        print(datetime.datetime.now(), "[INFO] Extract PDF Completed")


    if PIPELINE["dedoc_parse"]:
        print(datetime.datetime.now(), "[INFO] Dedoc parse start")
        dedoc_json = parse_pdf()
        os.remove(TEMP_PDF)

        with open(RAW_DEDOC_JSON, "w", encoding="utf-8") as f:
            json.dump(dedoc_json, f, ensure_ascii=False, indent=2)
    else:
        with open(RAW_DEDOC_JSON, "r", encoding="utf-8") as f:
            dedoc_json = json.load(f)

    print(datetime.datetime.now(), "[OK] Dedoc parse Completed")

    # ===============================
    # STEP 2 — Plain Text
    # ===============================
    if PIPELINE["extract_plain_text"]:
        print(datetime.datetime.now(), "[INFO] Plain Text Start")
        plain_blocks = extract_plain_blocks(dedoc_json)
        with open(PLAIN_JSON, "w", encoding="utf-8") as f:
            json.dump(plain_blocks, f, ensure_ascii=False, indent=2)
    else:
        with open(PLAIN_JSON, "r", encoding="utf-8") as f:
            plain_blocks = json.load(f)

    print(datetime.datetime.now(), "[OK] Plain Text Completed")
    # ===============================
    # STEP 3 — Chunking
    # ===============================
    print(datetime.datetime.now(), "[INFO] Chunker Start")
    chunker = TextChunker(max_chars=80000)
    chunks = chunker.chunk(plain_blocks)
    print(datetime.datetime.now(), "[OK] Chunker Completed")
    # ===============================
    # STEP 4 — LLM STRUCTURE
    # ===============================
    document = {
        "type": "document",
        "children": []
    }

    raw_llm_responses = []

    if PIPELINE["llm_structure"]:

        print(datetime.datetime.now(),"[INFO] LLM structure generate Start")

        for i, chunk in enumerate(chunks, 1):

            response = structure_llm.generate(
                system_prompt=SYSTEM_PROMPT,
                user_text=chunk["text"]
            )

            raw_llm_responses.append(response)

            chapters = safe_json_loads(response)

            for ch in chapters:
                document["children"].append(ch)

        # 1️⃣ сохраняем RAW
        with open(RAW_LLM_JSON, "w", encoding="utf-8") as f:
            json.dump(raw_llm_responses, f, ensure_ascii=False, indent=2)

        # 2️⃣ сохраняем STRUCTURED
        with open(STRUCTURED_JSON, "w", encoding="utf-8") as f:
            json.dump(document, f, ensure_ascii=False, indent=2)

    else:
        with open(STRUCTURED_JSON, "r", encoding="utf-8") as f:
            document = json.load(f)

    print(datetime.datetime.now(), "[OK] LLM structure generate Completed")
    # ===============================
    # STEP 5 — VALIDATE
    # ===============================
    print(datetime.datetime.now(), "[INFO] Validator Start")
    if PIPELINE["validate_schema"]:
        validator = JsonValidator(SCHEMA_PATH)
        errors = validator.validate(document)

        if errors:
            raise RuntimeError(errors)
    print(datetime.datetime.now(), "[OK] Validator Completed")
    # ===============================
    # SAVE STRUCTURE
    # ===============================
    with open(STRUCTURED_JSON, "w", encoding="utf-8") as f:
        json.dump(document, f, ensure_ascii=False, indent=2)

    print("[OK] Structure saved")

    # ===============================
    # STEP 6 — CLEAN TEXT
    # ===============================

    if PIPELINE["clean_text"]:
        print(datetime.datetime.now(), "[INFO] Text clean Start")
        from text_cleaner import TextCleaner

        cleaner = TextCleaner(cleaner_llm)
        document = cleaner.clean_document(document)

        with open(CLEAN_JSON, "w", encoding="utf-8") as f:
            json.dump(document, f, ensure_ascii=False, indent=2)

        print("[OK] Text clean Complete")


if __name__ == "__main__":
    run_pipeline()
