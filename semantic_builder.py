from typing import Dict, Any, List, Optional
from statistics import median
import json

from text_utils import strip_leading_markers, normalize_text


# ======================================================
# ИЗВЛЕЧЕНИЕ ПРИЗНАКОВ
# ======================================================

def extract_max_size(node: Dict[str, Any]) -> float:
    sizes = []
    for ann in node.get("annotations", []):
        if ann.get("name") == "size":
            try:
                sizes.append(float(ann["value"]))
            except ValueError:
                pass
    return max(sizes) if sizes else 0.0


def normalize_size(size: float, step: float = 0.5) -> float:
    if size <= 0:
        return 0.0
    return round(size / step) * step


def extract_spacing(node: Dict[str, Any]) -> float:
    for ann in node.get("annotations", []):
        if ann.get("name") == "spacing":
            try:
                return float(ann["value"])
            except ValueError:
                pass
    return 0.0


def extract_y_px(node: Dict[str, Any]) -> Optional[float]:
    for ann in node.get("annotations", []):
        if ann.get("name") == "bounding box":
            try:
                val = ann.get("value")
                bb = json.loads(val) if isinstance(val, str) else val
                y = bb.get("y_top_left")
                h = bb.get("page_height")
                if y is not None and h:
                    return float(y) * float(h)
            except Exception:
                pass
    return None


def extract_page(node: Dict[str, Any]) -> Optional[int]:
    return node.get("metadata", {}).get("page_id")


# ======================================================
# ФИЛЬТРАЦИЯ
# ======================================================

def is_noise(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if t.isdigit():
        return True
    if len(t) <= 2 and not t.isalpha():
        return True
    return False


def looks_like_heading(text: str) -> bool:
    """
    Короткий номинативный заголовок.
    Никаких правил про регистр.
    """
    if len(text) > 120:
        return False
    if text.count('.') >= 2:
        return False
    return True


# ======================================================
# СКЛЕЙКА СТРОК (КЛЮЧЕВОЙ БЛОК)
# ======================================================

def merge_lines(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Склеивает физические строки в логические.
    Решает:
    - курсив
    - переносы слов
    - разрывы одной строки на несколько node
    """
    merged: List[Dict[str, Any]] = []

    for b in blocks:
        if not merged:
            merged.append(b)
            continue

        last = merged[-1]

        # критерии "продолжения строки"
        same_size = abs(last["size"] - b["size"]) <= 0.5
        close_vertically = (
            last["dy_norm"] is not None and
            b["dy_norm"] is not None and
            b["dy_norm"] < 0.7
        )

        if same_size and close_vertically:
            # перенос слова
            if last["text"].endswith("-"):
                last["text"] = last["text"][:-1] + b["text"]
            else:
                last["text"] += " " + b["text"]
            continue

        # новая логическая строка
        merged.append(b)

    return merged


# ======================================================
# ОСНОВНОЙ API
# ======================================================

def build_semantic_hierarchy(dedoc_json: Dict[str, Any]) -> Dict[str, Any]:
    root = dedoc_json["content"]["structure"]

    raw_blocks: List[Dict[str, Any]] = []

    prev_y = None
    prev_page = None
    dy_values: List[float] = []

    # ---------- сбор плоских блоков ----------

    def walk(node: Dict[str, Any]):
        nonlocal prev_y, prev_page

        raw = node.get("text", "")
        text = normalize_text(strip_leading_markers(raw))

        if text and not is_noise(text):
            size = normalize_size(extract_max_size(node))
            spacing = extract_spacing(node)
            y = extract_y_px(node)
            page = extract_page(node)

            dy = None
            if y is not None and prev_y is not None and page == prev_page:
                delta = y - prev_y
                if delta > 0:
                    dy = delta
                    dy_values.append(delta)

            raw_blocks.append({
                "text": text,
                "size": size,
                "spacing": spacing,
                "dy": dy,
                "dy_norm": None
            })

            if y is not None:
                prev_y = y
                prev_page = page

        for ch in node.get("subparagraphs", []):
            walk(ch)

    walk(root)

    # ---------- нормализация dy ----------

    if dy_values:
        m = median(dy_values)
        for b in raw_blocks:
            if b["dy"] is not None:
                b["dy_norm"] = b["dy"] / m

    # ---------- СКЛЕЙКА СТРОК ----------
    merged_blocks = merge_lines(raw_blocks)

    # ---------- пороги ----------
    sizes = sorted(b["size"] for b in merged_blocks if b["size"] > 0)
    if not sizes:
        return {"chapters": []}

    p75 = sizes[int(len(sizes) * 0.75)]
    p90 = sizes[int(len(sizes) * 0.90)]

    # ---------- сбор структуры ----------
    document = {"chapters": []}

    current_chapter = None
    current_section = None

    for b in merged_blocks:
        text = b["text"]
        size = b["size"]

        # chapter
        if size >= p90 and looks_like_heading(text):
            current_chapter = {
                "chapter": text,
                "sections": []
            }
            document["chapters"].append(current_chapter)
            current_section = None
            continue

        # section
        if current_chapter and size >= p75 and looks_like_heading(text):
            # ПРОДОЛЖЕНИЕ ЗАГОЛОВКА
            if (
                    current_section is not None
                    and current_section["text"] == ""
                    and text[:1].islower()
            ):
                current_section["section"] += " " + text
                continue

            current_section = {
                "section": text,
                "text": ""
            }
            current_chapter["sections"].append(current_section)
            continue

        # обычный текст
        if current_chapter:
            if current_section is None:
                current_section = {
                    "section": None,
                    "text": ""
                }
                current_chapter["sections"].append(current_section)

            if current_section["text"]:
                current_section["text"] += "\n\n" + text
            else:
                current_section["text"] = text

    return document
