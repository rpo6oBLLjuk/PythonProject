import re
from typing import Dict, Any, List
from statistics import median
import numpy as np


# ======================================================
# УТИЛИТЫ
# ======================================================

MARKER_RE = re.compile(r'^[®@Ф\\#]+\s+')


def strip_leading_markers(text: str) -> str:
    return MARKER_RE.sub('', text).strip()


def merge_adjacent_text(blocks: List[Any]) -> List[Any]:
    """
    Склеивает подряд идущие текстовые строки.
    Узлы (dict с content) не трогает.
    """
    if not blocks:
        return []

    merged: List[Any] = [blocks[0]]

    for b in blocks[1:]:
        last = merged[-1]

        # строка + строка → склеиваем
        if isinstance(last, str) and isinstance(b, str):
            merged[-1] = last + "\n" + b
        else:
            merged.append(b)

    return merged


# ======================================================
# СБОР ПРИЗНАКОВ
# ======================================================

def collect_sizes_and_spacings(node: Dict[str, Any], sizes: List[float], spacings: List[float]):
    for ann in node.get("annotations", []):
        if ann["name"] == "size":
            try:
                sizes.append(float(ann["value"]))
            except ValueError:
                pass
        elif ann["name"] == "spacing":
            try:
                spacings.append(float(ann["value"]))
            except ValueError:
                pass

    for child in node.get("subparagraphs", []):
        collect_sizes_and_spacings(child, sizes, spacings)


def max_size(node: Dict[str, Any]) -> float:
    vals = [
        float(a["value"])
        for a in node.get("annotations", [])
        if a["name"] == "size"
    ]
    return max(vals) if vals else 0


def max_spacing(node: Dict[str, Any]) -> float:
    vals = [
        float(a["value"])
        for a in node.get("annotations", [])
        if a["name"] == "spacing"
    ]
    return max(vals) if vals else 0


# ======================================================
# ПРОФИЛЬ ДОКУМЕНТА
# ======================================================

class FontProfile:
    """
    Профиль документа для вычисления уровней заголовков.
    """

    def __init__(self, sizes: List[float], spacings: List[float]):
        self.sizes = [s for s in sizes if 8 <= s <= 80]
        self.spacings = [s for s in spacings if 10 <= s <= 300]

        if not self.sizes:
            raise ValueError("Нет валидных размеров")

        self.p50 = median(self.sizes)
        self.p75 = np.percentile(self.sizes, 75)
        self.p90 = np.percentile(self.sizes, 90)

        self.spacing_ref = (
            np.percentile(self.spacings, 75) if self.spacings else 40
        )

    def heading_level(self, size: float, spacing: float, text: str) -> int:
        text = text.strip()

        # --- жёсткие фильтры ---
        if not text:
            return -1

        if text.isdigit():
            return -1

        if len(text) > 120:
            return -1

        # --- собственно уровни ---
        if size >= self.p90 and spacing >= self.spacing_ref:
            return 0

        if size >= self.p75 and spacing >= self.spacing_ref * 0.7:
            return 1

        if size >= self.p75:
            return 2

        return -1


# ======================================================
# ОСНОВНОЙ API
# ======================================================

def build_semantic_hierarchy(dedoc_json: Dict[str, Any]) -> Dict[str, Any]:
    root = dedoc_json["content"]["structure"]

    sizes: List[float] = []
    spacings: List[float] = []
    collect_sizes_and_spacings(root, sizes, spacings)

    profile = FontProfile(sizes, spacings)

    document = {"chapters": []}
    node_stack: List[Dict[str, Any]] = []

    def push_node(text: str, level: int):
        nonlocal node_stack

        if level == 0:
            node = {
                "chapter": text,
                "content": []
            }
        elif level == 1:
            node = {
                "part": text,
                "content": []
            }
        else:
            node = {
                "name": text,
                "content": []
            }

        while len(node_stack) > level:
            node_stack.pop()

        if node_stack:
            node_stack[-1]["content"].append(node)
        else:
            document["chapters"].append(node)

        node_stack.append(node)

    def add_text(text: str):
        if not node_stack:
            return

        node_stack[-1]["content"].append(text)

    def walk(node: Dict[str, Any]):
        raw = node.get("text", "")
        text = strip_leading_markers(raw)

        if text:
            size = max_size(node)
            spacing = max_spacing(node)
            level = profile.heading_level(size, spacing, text)

            if level != -1:
                push_node(text, level)
            else:
                add_text(text)

        for child in node.get("subparagraphs", []):
            walk(child)

    walk(root)

    # пост-обработка: склейка текста
    def normalize(node: Dict[str, Any]):
        node["content"] = merge_adjacent_text(node["content"])
        for item in node["content"]:
            if isinstance(item, dict) and "content" in item:
                normalize(item)

    for ch in document["chapters"]:
        normalize(ch)

    return document
