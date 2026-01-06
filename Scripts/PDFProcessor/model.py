from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any


@dataclass(frozen=True)
class Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float
    is_bold: bool

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Paragraph:
    headers: List[str]
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return {"headers": self.headers, "text": self.text}


@dataclass
class Chapter:
    title: str
    headers: List[str]
    paragraphs: List[Paragraph]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "headers": self.headers,
            "paragraphs": [p.to_dict() for p in self.paragraphs],
        }
