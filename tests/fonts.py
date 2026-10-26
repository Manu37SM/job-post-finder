"""Cross-platform font lookup for tests that draw text onto synthetic images.

Tests used a hard-coded Linux DejaVu path, so every image-drawing test failed
with "OSError: cannot open resource" on Windows CI. Try common bold fonts per
OS, then fall back to Pillow's built-in scalable default font.
"""

from PIL import ImageFont

_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Debian/Ubuntu
    "DejaVuSans-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",  # Windows
    r"C:\Windows\Fonts\arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
    "Arial Bold.ttf",
]


def bold_font(size: int):
    for candidate in _CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size)
