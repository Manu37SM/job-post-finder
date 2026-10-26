"""
OCR provider interface, plus a cheap pre-filter so we don't run OCR on every
image a post links to - per spec, most post images are avatars/logos/reaction
GIFs, not "hiring poster" flyers.

Providers are config-driven (`ocr_provider` in config.json) so a second
provider can be added later without touching callers - see get_ocr_provider().
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image, UnidentifiedImageError


@dataclass
class OcrResult:
    text: str
    success: bool
    error: str | None = None


class OcrProvider(Protocol):
    def extract_text(self, image_path: str | Path) -> OcrResult: ...


# Deliberately generous, not clever: a false negative here (skipping a real
# flyer) is worse than one wasted OCR call, so these only filter out images
# that are almost certainly not text-bearing graphics.
MIN_DIMENSION_PX = 150
MAX_ASPECT_RATIO = 6.0


def is_worth_ocr(image_path: str | Path) -> bool:
    """Reads image dimensions only (no full pixel decode) to decide if OCR is worth running."""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
    except (FileNotFoundError, UnidentifiedImageError, OSError):
        # Can't even open it - let the actual OCR call fail and log the real reason.
        return True

    if width < MIN_DIMENSION_PX or height < MIN_DIMENSION_PX:
        return False

    aspect = max(width, height) / max(1, min(width, height))
    if aspect > MAX_ASPECT_RATIO:
        return False

    return True


def get_ocr_provider(name: str, tesseract_cmd: str | None = None) -> OcrProvider:
    if name == "tesseract":
        from ocr.tesseract import TesseractOcrProvider

        return TesseractOcrProvider(tesseract_cmd=tesseract_cmd)
    raise ValueError(f"Unknown ocr_provider: {name!r}")
