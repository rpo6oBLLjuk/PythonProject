import json
import re


def safe_json_loads(text: str):
    """
    Извлекает ВСЕ JSON-объекты из строки.
    Возвращает список объектов.
    """

    if not text:
        raise ValueError("Empty LLM response")

    # Убираем markdown
    text = re.sub(r"```json", "", text)
    text = re.sub(r"```", "", text)

    objects = []
    brace_stack = 0
    start = None

    for i, ch in enumerate(text):
        if ch == "{":
            if brace_stack == 0:
                start = i
            brace_stack += 1

        elif ch == "}":
            brace_stack -= 1

            if brace_stack == 0 and start is not None:
                candidate = text[start:i + 1]
                try:
                    obj = json.loads(candidate)
                    objects.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None

    if not objects:
        raise ValueError("No valid JSON objects found")

    return objects
