import time


CLEAN_PROMPT = """
Очисти текст:

- убери переносы внутри слов
- убери случайные цифры страниц
- убери мусорные символы
- сохрани исходный текст
- не перефразируй
- верни только очищенный текст
"""


class TextCleaner:

    def __init__(self, llm):
        self.llm = llm

    def clean_text(self, text: str) -> str:
        t0 = time.time()

        cleaned = self.llm.generate(
            system_prompt=CLEAN_PROMPT,
            user_text=text
        )

        print(f"[CLEAN] {len(text)} → {len(cleaned)} | {time.time() - t0:.1f}s")

        return cleaned.strip()

    def clean_section(self, section: dict) -> dict:
        section["text"] = self.clean_text(section["text"])
        return section

    def clean_paragraph(self, paragraph: dict) -> dict:
        for section in paragraph["children"]:
            self.clean_section(section)
        return paragraph

    def clean_chapter(self, chapter: dict) -> dict:
        for paragraph in chapter["children"]:
            self.clean_paragraph(paragraph)
        return chapter

    def clean_document(self, document: dict) -> dict:
        for chapter in document["children"]:
            self.clean_chapter(chapter)
        return document
