import json
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict, Any
import re
from PySide6.QtCore import QObject


@dataclass
class TextElementData:
    """Упрощенная структура для передачи через сигналы"""
    text: str
    element_type: str
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    is_bold: bool = False
    is_italic: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "type": self.element_type,
            "font_name": self.font_name,
            "font_size": self.font_size,
            "is_bold": self.is_bold,
            "is_italic": self.is_italic
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TextElementData':
        return cls(
            text=data["text"],
            element_type=data["type"],
            font_name=data.get("font_name"),
            font_size=data.get("font_size"),
            is_bold=data.get("is_bold", False),
            is_italic=data.get("is_italic", False)
        )


class PageData(QObject):
    """Класс для хранения данных страницы"""

    def __init__(self, page_number: int):
        super().__init__()
        self.page_number = page_number
        self.elements: List[TextElementData] = []

    def add_element(self, element: TextElementData):
        self.elements.append(element)

    def to_json(self) -> str:
        """Конвертация в JSON строку"""
        data = {
            "page_number": self.page_number,
            "elements": [elem.to_dict() for elem in self.elements]
        }
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'PageData':
        """Создание из JSON строки"""
        data = json.loads(json_str)
        page = cls(data["page_number"])
        for elem_data in data["elements"]:
            page.add_element(TextElementData.from_dict(elem_data))
        return page