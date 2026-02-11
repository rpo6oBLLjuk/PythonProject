from typing import List, Dict
import re


def strip_leading_markers(text: str) -> str:
    return re.sub(r"^[•–—*\d\)\.(]+\s*", "", text).strip()


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fix_lists(blocks: List[Dict]) -> List[Dict]:
    """
    Склеивает многострочные пункты списков.
    """
    fixed: List[Dict] = []
    buffer = None

    for block in blocks:
        text = block["text"]
        page = block.get("page")

        is_list_item = bool(re.match(r"^(\d+\.|[-•])\s+", text))

        if is_list_item:
            if buffer:
                fixed.append(buffer)
            buffer = {
                "page": page,
                "text": text
            }
        else:
            if buffer:
                buffer["text"] += " " + text
            else:
                fixed.append(block)
                buffer = None

    if buffer:
        fixed.append(buffer)

    return fixed


def preprocess_text(blocks: List[Dict]) -> List[Dict]:
    cleaned: List[Dict] = []

    for block in blocks:
        text = block["text"]
        text = strip_leading_markers(text)
        text = normalize_whitespace(text)

        if not text:
            continue

        cleaned.append({
            "page": block.get("page"),
            "text": text
        })

    return fix_lists(cleaned)
