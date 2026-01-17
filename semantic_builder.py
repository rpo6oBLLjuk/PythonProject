import re
from typing import Dict, Any, List
from statistics import median
import numpy as np

from toc_parser import parse_toc

# ======================================================
# УТИЛИТЫ ТЕКСТА
# ======================================================

MARKER_RE = re.compile(r'^[®@Ф\\#]+\s+')


def strip_leading_markers(text: str) -> str:
    return MARKER_RE.sub('', text).strip()


def is_noise(text: str) -> bool:
    t = text.strip()

    if not t:
        return True

    if t.isdigit():
        return True

    if len(t) <= 2 and not t.isalpha():
        return True

    return False


def normalize_text(text: str) -> str:
    text = re.sub(r'-\s*\n\s*', '', text)
    text = text.replace('\r\n', '\n')
    text = re.sub(r'\n{2,}', '\n\n', text)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    return text.strip()


def merge_adjacent_text(block_content: List[str]) -> List[str]:
    if not block_content:
        return []

    text = "\n\n".join(
        normalize_text(t)
        for t in block_content
        if t.strip()
    )

    text = re.sub(r'\n{3,}', '\n\n', text)
    return [text]


# ======================================================
# СБОР ПРИЗНАКОВ
# ======================================================

def collect_sizes_and_spacings(node: Dict[str, Any],
                               sizes: List[float],
                               spacings: List[float]):
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
        t = text.strip()

        if len(t) > 120:
            return -1
        if t.count('.') >= 2:
            return -1

        if size >= self.p90 and spacing >= self.spacing_ref:
            return 0
        if size >= self.p75:
            return 1
        if size >= self.p50 * 1.1:
            return 2

        return -1


# ======================================================
# ОСНОВНОЙ API
# ======================================================

def build_semantic_hierarchy(dedoc_json: Dict[str, Any]) -> Dict[str, Any]:
    toc_map = parse_toc(dedoc_json)
    print(f"[TOC] Найдено элементов: {len(toc_map)}")

    root = dedoc_json["content"]["structure"]

    sizes: List[float] = []
    spacings: List[float] = []
    collect_sizes_and_spacings(root, sizes, spacings)

    profile = FontProfile(sizes, spacings)

    document = {"chapters": []}

    current_chapter = None
    current_part = None
    current_block = None
    chapter_has_content = False   # <<< ДОБАВЛЕНО

    # ---------------- helpers ----------------

    def ensure_chapter(title: str = "Без названия"):
        nonlocal current_chapter, current_part, current_block, chapter_has_content
        if current_chapter is None:
            current_chapter = {
                "chapter": title,
                "content": []
            }
            document["chapters"].append(current_chapter)
            current_part = None
            current_block = None
            chapter_has_content = False   # <<<

    def ensure_part(name=None):
        nonlocal current_part, current_block
        if current_part is None:
            current_part = {
                "part": name,
                "content": []
            }
            current_chapter["content"].append(current_part)
            current_block = None

    def ensure_block(name=None):
        nonlocal current_block
        ensure_part()
        if current_block is None:
            current_block = {
                "block": name,
                "content": []
            }
            current_part["content"].append(current_block)

    # ---------------- walk ----------------

    def walk(node: Dict[str, Any]):
        nonlocal current_chapter, current_part, current_block, chapter_has_content

        raw = node.get("text", "")
        text = strip_leading_markers(raw)

        if text:
            if is_noise(text):
                pass
            else:
                size = max_size(node)
                spacing = max_spacing(node)

                normalized = normalize_text(text)

                if normalized in toc_map:
                    print("[TOC MATCH]", repr(normalized))
                    level = toc_map[normalized]
                else:
                    level = profile.heading_level(size, spacing, text)

                # --------- ГЛАВА (ИСПРАВЛЕНИЕ ЗДЕСЬ) ---------
                if level == 0:
                    if current_chapter is None or not chapter_has_content:
                        current_chapter = {
                            "chapter": text,
                            "content": []
                        }
                        document["chapters"].append(current_chapter)
                        current_part = None
                        current_block = None
                        chapter_has_content = False
                    else:
                        ensure_chapter()
                        ensure_part()
                        current_block = {
                            "block": text,
                            "content": []
                        }
                        current_part["content"].append(current_block)

                elif level == 1:
                    ensure_chapter()
                    current_part = {
                        "part": text,
                        "content": []
                    }
                    current_chapter["content"].append(current_part)
                    current_block = None

                elif level == 2:
                    ensure_chapter()
                    ensure_part()
                    current_block = {
                        "block": text,
                        "content": []
                    }
                    current_part["content"].append(current_block)

                else:
                    ensure_chapter()
                    ensure_part()
                    ensure_block()
                    current_block["content"].append(text)
                    chapter_has_content = True   # <<< ВАЖНО

        for child in node.get("subparagraphs", []):
            walk(child)

    walk(root)

    # ---------------- normalize ----------------

    for ch in document["chapters"]:
        for part in ch["content"]:
            for block in part["content"]:
                block["content"] = merge_adjacent_text(block["content"])

    return document
