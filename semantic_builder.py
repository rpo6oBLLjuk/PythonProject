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
# ФИЛЬТРЫ
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
    Короткий номинативный заголовок
    """
    if len(text) > 120:
        return False
    if text.count('.') >= 2:
        return False
    return True


# ======================================================
# ОСНОВНОЙ API
# ======================================================

def build_semantic_hierarchy(dedoc_json: Dict[str, Any]) -> Dict[str, Any]:
    root = dedoc_json["content"]["structure"]

    blocks: List[Dict[str, Any]] = []

    prev_y = None
    prev_page = None
    dy_values: List[float] = []

    # -------- сбор плоских блоков --------

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

            blocks.append({
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

    # -------- нормализация dy --------

    if dy_values:
        m = median(dy_values)
        for b in blocks:
            if b["dy"] is not None:
                b["dy_norm"] = b["dy"] / m

    # -------- пороги --------

    sizes = sorted(b["size"] for b in blocks if b["size"] > 0)
    if not sizes:
        return {"chapters": []}

    p75 = sizes[int(len(sizes) * 0.75)]
    p90 = sizes[int(len(sizes) * 0.90)]

    # -------- сбор структуры --------

    document = {"chapters": []}

    current_chapter = None
    current_section = None

    for b in blocks:
        text = b["text"]
        size = b["size"]
        dy = b["dy_norm"]

        # --- chapter ---
        if size >= p90 and looks_like_heading(text):
            current_chapter = {
                "chapter": text,
                "sections": []
            }
            document["chapters"].append(current_chapter)
            current_section = None
            continue

        # --- section ---
        if (
            current_chapter
            and size >= p75
            and looks_like_heading(text)
        ):
            current_section = {
                "section": text,
                "text": ""
            }
            current_chapter["sections"].append(current_section)
            continue

        # --- обычный текст ---
        if current_chapter:
            if current_section is None:
                # section = null
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
