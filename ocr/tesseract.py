"""
Tesseract-backed OcrProvider. Grayscale + fixed threshold preprocessing
noticeably improves accuracy on typical solid-background "hiring poster"
graphics versus feeding tesseract the raw image - not attempting adaptive
thresholding or deskewing in v1.

Never raises: every failure mode (missing file, corrupt image, tesseract
binary missing) comes back as OcrResult(success=False, error=...) so the
caller can log it and move on to the next image, per spec.

WINDOWS NOTE: pytesseract (the Python package) and Tesseract (the actual
OCR binary) are separate installs - `pip install pytesseract` alone does
NOT get you a working OCR pipeline. On Linux/Mac, installing via
apt/brew puts `tesseract` on PATH and pytesseract finds it automatically.
On Windows, the official installer does not reliably add it to PATH, so
every image fails OCR with a "tesseract is not installed or it's not in
your PATH" error - this is exactly what "OCR successes: 0, OCR failures: N"
for every processed image means. _auto_detect() below checks the two
default Windows install locations as a fallback before giving up; if
Tesseract was installed somewhere else, set `tesseract_cmd` in
config.json to its full path.
"""

import shutil
from pathlib import Path

from PIL import Image, ImageOps

from ocr.engine import OcrResult

_COMMON_WINDOWS_INSTALL_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


class TesseractOcrProvider:
    def __init__(self, tesseract_cmd: str | None = None):
        """
        tesseract_cmd: explicit path to the tesseract binary (set via
        config.json's "tesseract_cmd"). If None, tries the bare
        "tesseract" command on PATH first, then falls back to checking the
        common Windows install locations above - see module docstring for
        why this fallback exists.
        """
        self._tesseract_cmd = tesseract_cmd or self._auto_detect()

    @staticmethod
    def _auto_detect() -> str | None:
        if shutil.which("tesseract"):
            return None  # already on PATH - let pytesseract use its own default
        for path in _COMMON_WINDOWS_INSTALL_PATHS:
            if Path(path).exists():
                return path
        return None  # nothing found - extract_text() below will surface the real error

    def extract_text(self, image_path: str | Path) -> OcrResult:
        try:
            import pytesseract
        except ImportError as e:
            return OcrResult(text="", success=False, error=f"pytesseract not installed: {e}")

        if self._tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd

        try:
            with Image.open(image_path) as img:
                text = pytesseract.image_to_string(self._preprocess(img)).strip()
                # Recall fallback (v11): the fixed threshold-150 pass blanks
                # out coloured / dark-background flyers, which is where
                # "sometimes no email" came from on image posts. If the first
                # pass found no '@', retry with gentler variants and keep any
                # extra lines they find. Cheap: only runs when nothing was found.
                if "@" not in text:
                    for variant in self._fallback_variants(img):
                        extra = pytesseract.image_to_string(variant).strip()
                        text = self._merge(text, extra)
                        if "@" in text:
                            break
            return OcrResult(text=text, success=True)
        except Exception as e:  # noqa: BLE001 - OCR must never crash the run
            error = str(e)
            if "not installed" in error.lower() or "not in your path" in error.lower():
                error += (
                    " -- set \"tesseract_cmd\" in config.json to tesseract.exe's full "
                    r"path (commonly C:\Program Files\Tesseract-OCR\tesseract.exe on "
                    "Windows), or add its folder to your PATH."
                )
            return OcrResult(text="", success=False, error=error)

    @staticmethod
    def _merge(base: str, extra: str) -> str:
        have = {ln.strip() for ln in base.splitlines()}
        new = [ln for ln in extra.splitlines() if ln.strip() and ln.strip() not in have]
        return "\n".join(filter(None, [base, *new]))

    @staticmethod
    def _fallback_variants(img: Image.Image):
        """Yield alternative preprocessings, lazily so we stop at the first hit."""
        gray = ImageOps.autocontrast(ImageOps.grayscale(img))
        if max(gray.size) < 1600:  # small flyers OCR much better when enlarged
            gray = gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)
        yield gray
        yield ImageOps.invert(gray)  # light text on dark background

    @staticmethod
    def _preprocess(img: Image.Image) -> Image.Image:
        gray = ImageOps.grayscale(img)
        return gray.point(lambda p: 255 if p > 150 else 0)
