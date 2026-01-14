import re
from typing import Dict, Any, List
from statistics import median
import numpy as np


# ======================================================
# СЛУЖЕБНЫЕ УТИЛИТЫ
# ======================================================

MARKER_RE = re.compile(r'^[®@Ф\\#]+\s+')


def strip_leading_markers(text: str) -> str:
    """
    Убирает ведущие служебные маркеры вида:
    '® Текст', '@@   Текст', 'Ф  Текст'
    """
    return MARKER_RE.sub('', text).strip()


def merge_adjacent_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Склеивает подряд идущие блоки одного типа.
    """
    if not blocks:
        return []

    merged = [blocks[0].copy()]

    for block in blocks[1:]:
        last = merged[-1]

        if block["type"] == last["type"]:
            last["text"] += "\n" + block["text"]
        else:
            merged.append(block.copy())

    return merged


# ======================================================
# СБОР ПРИЗНАКОВ
# ======================================================

def collect_font_sizes(node: Dict[str, Any], acc: List[float]):
    for ann in node.get("annotations", []):
        if ann["name"] == "size":
            try:
                acc.append(float(ann["value"]))
            except ValueError:
                pass
    for child in node.get("subparagraphs", []):
        collect_font_sizes(child, acc)


def collect_spacings(node: Dict[str, Any], acc: List[float]):
    for ann in node.get("annotations", []):
        if ann["name"] == "spacing":
            try:
                acc.append(float(ann["value"]))
            except ValueError:
                pass
    for child in node.get("subparagraphs", []):
        collect_spacings(child, acc)


def max_font_size(node: Dict[str, Any]) -> float:
    sizes = [
        float(a["value"])
        for a in node.get("annotations", [])
        if a["name"] == "size"
    ]
    return max(sizes) if sizes else 0


# ======================================================
# ПРОФИЛЬ ДОКУМЕНТА
# ======================================================

class FontProfile:
    """
    Устойчивый профиль шрифтов для учебников.
    """

    def __init__(self, raw_sizes: List[float], raw_spacings: List[float]):
        self.sizes = self._normalize_sizes(raw_sizes)

        if not self.sizes:
            raise ValueError("Нет валидных размеров шрифтов")

        self.median = median(self.sizes)
        self.p75 = np.percentile(self.sizes, 75)
        self.p90 = np.percentile(self.sizes, 90)

        # пороги по размеру
        self.chapter_threshold = self.p90
        self.section_threshold = max(self.p75, self.median * 1.15)

        # порог по spacing
        spacings = [s for s in raw_spacings if 10 <= s <= 300]
        self.spacing_chapter_threshold = (
            np.percentile(spacings, 75) if spacings else 40
        )

    @staticmethod
    def _normalize_sizes(sizes: List[float]) -> List[float]:
        """
        Убирает OCR-мусор и декоративные элементы.
        """
        return [s for s in sizes if 8 <= s <= 80]


# ======================================================
# КЛАССИФИКАЦИЯ
# ======================================================

def classify(node: Dict[str, Any], profile: FontProfile) -> str:
    raw_text = node.get("text", "")
    text = strip_leading_markers(raw_text)

    if not text:
        return "ignore"

    size = max_font_size(node)

    # защита от OCR-мусора
    if size < 8 or size > 80:
        return "ignore"

    spacing_values = [
        float(a["value"])
        for a in node.get("annotations", [])
        if a["name"] == "spacing"
    ]
    spacing = max(spacing_values) if spacing_values else 0

    # ---------
    # ГЛАВА
    # ---------
    if (
        size >= profile.chapter_threshold
        and spacing >= profile.spacing_chapter_threshold
    ):
        return "chapter"

    # ---------
    # РАЗДЕЛ
    # ---------
    if size >= profile.section_threshold:
        return "section"

    return "text"


# ======================================================
# ОСНОВНОЙ API
# ======================================================

def build_semantic_hierarchy(dedoc_json: Dict[str, Any]) -> Dict[str, Any]:
    root = dedoc_json["content"]["structure"]

    # --- сбор статистики ---
    sizes: List[float] = []
    spacings: List[float] = []

    collect_font_sizes(root, sizes)
    collect_spacings(root, spacings)

    profile = FontProfile(sizes, spacings)

    document = {"chapters": []}

    current_chapter = None
    current_section = None

    def walk(node: Dict[str, Any]):
        nonlocal current_chapter, current_section

        raw_text = node.get("text", "")
        text = strip_leading_markers(raw_text)
        kind = classify(node, profile)

        if kind == "chapter":
            current_chapter = {
                "type": "chapter",
                "title": text,
                "sections": [],
                "content": []
            }
            document["chapters"].append(current_chapter)
            current_section = None

        elif kind == "section" and current_chapter:
            current_section = {
                "type": "section",
                "title": text,
                "content": []
            }
            current_chapter["sections"].append(current_section)

        elif kind == "text":
            target = None

            if current_section:
                target = current_section["content"]
            elif current_chapter:
                target = current_chapter["content"]

            if target is not None:
                target.append({
                    "type": "text",
                    "text": text
                })

        for child in node.get("subparagraphs", []):
            walk(child)

    # --- обход дерева ---
    walk(root)

    # --- пост-обработка: слияние блоков ---
    for chapter in document.get("chapters", []):
        chapter["content"] = merge_adjacent_blocks(chapter.get("content", []))

        for section in chapter.get("sections", []):
            section["content"] = merge_adjacent_blocks(section.get("content", []))

    return document
