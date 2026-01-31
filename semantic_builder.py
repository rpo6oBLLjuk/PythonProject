import json
from typing import Dict, Any, List, Optional
from statistics import median

from text_utils import (
    strip_leading_markers,
    normalize_text
)


# ======================================================
# ИЗВЛЕЧЕНИЕ ПРИЗНАКОВ ИЗ DEDOC
# ======================================================

def extract_max_size(node: Dict[str, Any]) -> float:
    """
    Максимальный размер шрифта в узле
    """
    sizes = []
    for ann in node.get("annotations", []):
        if ann.get("name") == "size":
            try:
                sizes.append(float(ann["value"]))
            except ValueError:
                pass
    return max(sizes) if sizes else 0.0


def normalize_size(size: float, step: float = 0.5) -> float:
    """
    Квантизация размера шрифта для устранения шума (14 ↔ 15)
    """
    if size <= 0:
        return 0.0
    return round(size / step) * step


def extract_spacing(node: Dict[str, Any]) -> float:
    """
    Межстрочный / межблочный интервал, если dedoc его дал
    """
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
                value = ann.get("value")

                if isinstance(value, str):
                    bb = json.loads(value)
                elif isinstance(value, dict):
                    bb = value
                else:
                    continue

                y_norm = bb.get("y_top_left")
                page_h = bb.get("page_height")

                if y_norm is not None and page_h:
                    return float(y_norm) * float(page_h)

            except Exception:
                pass
    return None


def extract_page(node: Dict[str, Any]) -> Optional[int]:
    return node.get("metadata", {}).get("page_id")


# ======================================================
# ФИЛЬТРАЦИЯ МУСОРА
# ======================================================

def is_noise(text: str) -> bool:
    t = text.strip()

    if not t:
        return True

    # номера страниц
    if t.isdigit():
        return True

    # короткий мусор
    if len(t) <= 2 and not t.isalpha():
        return True

    return False


# ======================================================
# ОСНОВНОЙ API
# ======================================================

def build_semantic_hierarchy(dedoc_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Формирует ПЛОСКИЙ список блоков:

    {
      "blocks": [
        {
          "text": str,
          "size": float,
          "spacing": float,
          "dy": float | None,
          "dy_norm": float | None,
          "page": int
        }
      ]
    }
    """

    root = dedoc_json["content"]["structure"]

    blocks: List[Dict[str, Any]] = []

    prev_y: Optional[float] = None
    prev_page: Optional[int] = None

    # временно собираем dy для нормализации
    raw_dy_values: List[float] = []

    # ---------------- обход документа ----------------

    def walk(node: Dict[str, Any]):
        nonlocal prev_y, prev_page

        raw = node.get("text", "")
        text = strip_leading_markers(raw)

        if text:
            text = normalize_text(text)

            if not is_noise(text):
                size_raw = extract_max_size(node)
                size = normalize_size(size_raw)

                spacing = extract_spacing(node)
                y = extract_y_px(node)
                page = extract_page(node)

                dy: Optional[float] = None

                if (
                    y is not None
                    and prev_y is not None
                    and page is not None
                    and page == prev_page
                ):
                    delta = y - prev_y
                    if delta > 0:
                        dy = delta
                        raw_dy_values.append(delta)

                blocks.append({
                    "text": text,
                    "size": size,
                    "spacing": spacing,
                    "dy": dy,
                    "dy_norm": None,   # заполним позже
                    "page": page
                })

                if y is not None:
                    prev_y = y
                    prev_page = page

        for child in node.get("subparagraphs", []):
            walk(child)

    walk(root)

    # ---------------- нормализация dy ----------------

    if raw_dy_values:
        median_line_height = median(raw_dy_values)
    else:
        median_line_height = None

    if median_line_height and median_line_height > 0:
        for block in blocks:
            if block["dy"] is not None:
                block["dy_norm"] = block["dy"] / median_line_height
    else:
        for block in blocks:
            block["dy_norm"] = None

    return {
        "blocks": blocks
    }
