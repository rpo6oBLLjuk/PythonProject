import os
from typing import Optional
from PIL import Image
from pdf2image import convert_from_path
import pytesseract

from Scripts.Utils.logger import Logger


def render_page_image(pdf_path: str, page_idx: int, poppler_bin: str, logger: Logger) -> Optional[Image.Image]:
    try:
        imgs = convert_from_path(
            pdf_path,
            first_page=page_idx + 1,
            last_page=page_idx + 1,
            dpi=250,
            fmt="png",
            use_pdftocairo=True,
            thread_count=4,
            poppler_path=poppler_bin,
        )
        return imgs[0] if imgs else None
    except Exception as e:
        logger.error("OCR fallback: render error", e)
        return None


def ocr_image(img: Image.Image, logger: Logger) -> str:
    try:
        try:
            return pytesseract.image_to_string(img, lang="rus")
        except Exception:
            return pytesseract.image_to_string(img)
    except Exception as e:
        logger.error("OCR fallback: tesseract error", e)
        return ""
