# ----------------------------
# Data model (new structure)
# ----------------------------
from dataclasses import dataclass
from typing import Dict, Literal

TextType = Literal[
    "header",
    "subheader",
    "task_number",
    "answer_option",
    "bold_text",
    "paragraph",
    "table",
    "image_text",
    "regular"
]


@dataclass
class TextItem:
    type: TextType
    text: str

    def to_dict(self) -> Dict[str, str]:
        return {"type": self.type, "text": self.text}