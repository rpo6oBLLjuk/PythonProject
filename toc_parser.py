import re
from typing import Dict, Any, List


PAGE_NUM_RE = re.compile(r'\s+(\d{1,4})\s*$')
DOTS_RE = re.compile(r'\.{2,}')


def normalize_toc_title(text: str) -> str:
    """
    Убирает точки-лидеры и номер страницы
    """
    text = PAGE_NUM_RE.sub('', text)
    text = DOTS_RE.sub('', text)
    return text.strip()


def extract_indent(node: Dict[str, Any]) -> float:
    """
    Пытаемся получить отступ слева (x0 или left)
    """
    for ann in node.get("annotations", []):
        if ann["name"] in ("x0", "left", "indent"):
            try:
                return float(ann["value"])
            except ValueError:
                pass
    return 0.0


def max_font_size(node: Dict[str, Any]) -> float:
    sizes = []
    for ann in node.get("annotations", []):
        if ann["name"] == "size":
            try:
                sizes.append(float(ann["value"]))
            except ValueError:
                pass
    return max(sizes) if sizes else 0.0


def parse_toc(dedoc_json: Dict[str, Any]) -> Dict[str, int]:
    """
    Возвращает карту:
    { title -> level }
    """
    root = dedoc_json["content"]["structure"]

    toc_lines: List[Dict[str, Any]] = []

    # 1. Собираем все строки, похожие на оглавление
    def walk(node):
        text = node.get("text", "").strip()
        if PAGE_NUM_RE.search(text):
            toc_lines.append({
                "raw": text,
                "title": normalize_toc_title(text),
                "indent": extract_indent(node),
                "size": max_font_size(node)
            })

        for ch in node.get("subparagraphs", []):
            walk(ch)

    walk(root)

    if not toc_lines:
        return {}

    # 2. Нормализуем отступы → уровни
    indents = sorted({line["indent"] for line in toc_lines})
    indent_to_level = {
        indent: idx
        for idx, indent in enumerate(indents)
    }

    toc_map: Dict[str, int] = {}

    for line in toc_lines:
        title = line["title"]
        level = indent_to_level.get(line["indent"], 0)
        toc_map[title] = level

    return toc_map
