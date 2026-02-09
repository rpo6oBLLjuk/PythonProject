from typing import Dict, Any, List, Optional
from statistics import median
import json
import re

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


def extract_bbox(node: Dict[str, Any]) -> Optional[Dict[str, float]]:
    for ann in node.get("annotations", []):
        if ann.get("name") == "bounding box":
            try:
                val = ann.get("value")
                return json.loads(val) if isinstance(val, str) else val
            except Exception:
                pass
    return None


def extract_y_px(node: Dict[str, Any]) -> Optional[float]:
    bb = extract_bbox(node)
    if not bb:
        return None
    try:
        return float(bb["y_top_left"]) * float(bb["page_height"])
    except Exception:
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
    if len(text) > 120:
        return False
    if text.count('.') >= 2:
        return False
    return True


# ======================================================
# СКЛЕЙКА ФИЗИЧЕСКИХ СТРОК
# ======================================================

def merge_lines(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []

    for b in blocks:
        if not merged:
            merged.append(b)
            continue

        last = merged[-1]

        same_size = abs(last["size"] - b["size"]) <= 0.5
        close_vertically = (
            last["dy_norm"] is not None and
            b["dy_norm"] is not None and
            b["dy_norm"] < 0.7
        )

        if same_size and close_vertically:
            if last["text"].endswith("-"):
                last["text"] = last["text"][:-1] + b["text"]
            else:
                last["text"] += "\n" + b["text"]
            continue

        merged.append(b)

    return merged


# ======================================================
# ПОСТ-ОБРАБОТКА СПИСКОВ
# ======================================================

LIST_ITEM_RE = re.compile(r'^\s*\d+[.)]')
INLINE_LIST_RE = re.compile(r'([^\n])\s+(\d+[.)]\s+)')


def fix_lists(text: str) -> str:
    """
    1. Склеивает продолжения пунктов списка
    2. Восстанавливает разрывы между пунктами
    """
    if not text:
        return text

    # --- восстановление разрывов между пунктами ---
    text = re.sub(r'([^\n])\s+(\d+[.)]\s+)', r'\1\n\n\2', text)

    parts = text.split("\n\n")
    fixed: List[str] = []

    for p in parts:
        p = p.strip()
        if not p:
            continue

        if (
            fixed
            and not LIST_ITEM_RE.match(p)
            and LIST_ITEM_RE.match(fixed[-1])
            and p[0].islower()
        ):
            fixed[-1] += " " + p
        else:
            fixed.append(p)

    return "\n\n".join(fixed)


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
        text = strip_leading_markers(raw)

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

    # ---------- склейка строк ----------
    merged_blocks = merge_lines(raw_blocks)

    # ---------- normalize_text ----------
    for b in merged_blocks:
        b["text"] = normalize_text(b["text"])

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
        dy_norm = b["dy_norm"]

        # CHAPTER
        if size >= p90 and looks_like_heading(text):
            current_chapter = {
                "chapter": text,
                "sections": []
            }
            document["chapters"].append(current_chapter)
            current_section = None
            continue

        # SECTION
        if (
            current_chapter
            and size >= p75
            and looks_like_heading(text)
            and (
                current_section is None
                or dy_norm is None
                or dy_norm >= 0.6
            )
        ):
            current_section = {
                "section": text,
                "text": ""
            }
            current_chapter["sections"].append(current_section)
            continue

        # TEXT
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

    # ---------- пост-обработка списков ----------
    for ch in document["chapters"]:
        for sec in ch["sections"]:
            sec["text"] = fix_lists(sec["text"])

    return document
