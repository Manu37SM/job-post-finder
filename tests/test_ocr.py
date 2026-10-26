from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from ocr.engine import get_ocr_provider, is_worth_ocr
from ocr.tesseract import TesseractOcrProvider

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _make_flyer(path: Path, lines: list[str], size=(600, 400)) -> None:
    """Synthetic 'hiring poster' image: white background, bold black text."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, 32)
    y = 30
    for line in lines:
        draw.text((30, y), line, fill="black", font=font)
        y += 50
    img.save(path)


# ---- is_worth_ocr pre-filter ----


def test_skips_small_icon(tmp_path):
    path = tmp_path / "icon.png"
    Image.new("RGB", (60, 60), "white").save(path)
    assert is_worth_ocr(path) is False


def test_skips_extreme_aspect_banner(tmp_path):
    path = tmp_path / "banner.png"
    Image.new("RGB", (1200, 60), "white").save(path)  # aspect 20:1
    assert is_worth_ocr(path) is False


def test_accepts_normal_flyer_dimensions(tmp_path):
    path = tmp_path / "flyer.png"
    Image.new("RGB", (600, 800), "white").save(path)
    assert is_worth_ocr(path) is True


def test_unreadable_file_defaults_to_worth_ocr(tmp_path):
    # Let the real OCR call fail (and log the actual error) rather than
    # silently skip a file we couldn't even inspect.
    missing = tmp_path / "does-not-exist.png"
    assert is_worth_ocr(missing) is True


# ---- TesseractOcrProvider ----


def test_extracts_text_from_synthetic_flyer(tmp_path):
    path = tmp_path / "flyer.png"
    _make_flyer(
        path,
        ["URGENT HIRING", "Java Developer", "Mumbai", "jobs@example.com"],
    )
    result = TesseractOcrProvider().extract_text(path)
    assert result.success is True
    assert result.error is None
    lowered = result.text.lower()
    assert "java" in lowered
    assert "mumbai" in lowered
    assert "jobs@example.com" in lowered


def test_missing_file_does_not_crash(tmp_path):
    missing = tmp_path / "does-not-exist.png"
    result = TesseractOcrProvider().extract_text(missing)
    assert result.success is False
    assert result.text == ""
    assert result.error is not None


def test_corrupt_image_does_not_crash(tmp_path):
    path = tmp_path / "corrupt.png"
    path.write_bytes(b"not actually a png")
    result = TesseractOcrProvider().extract_text(path)
    assert result.success is False
    assert result.error is not None


# ---- provider factory ----


def test_get_ocr_provider_tesseract():
    provider = get_ocr_provider("tesseract")
    assert isinstance(provider, TesseractOcrProvider)


def test_get_ocr_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_ocr_provider("some-other-provider")


def test_get_ocr_provider_passes_through_tesseract_cmd():
    provider = get_ocr_provider("tesseract", tesseract_cmd=r"C:\custom\tesseract.exe")
    assert provider._tesseract_cmd == r"C:\custom\tesseract.exe"


# ---- Windows tesseract_cmd auto-detection / override ----


def test_explicit_tesseract_cmd_is_used_verbatim():
    provider = TesseractOcrProvider(tesseract_cmd=r"C:\custom\tesseract.exe")
    assert provider._tesseract_cmd == r"C:\custom\tesseract.exe"


def test_auto_detect_finds_tesseract_already_on_path(monkeypatch):
    # This sandbox genuinely has tesseract on PATH (see test_extracts_text_
    # from_synthetic_flyer above, which uses real OCR) - the real-world case
    # this covers.
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/tesseract")
    provider = TesseractOcrProvider()
    # On PATH -> no explicit override needed, pytesseract uses its own default.
    assert provider._tesseract_cmd is None


def test_auto_detect_falls_back_to_windows_path_when_not_on_path(monkeypatch, tmp_path):
    import ocr.tesseract as tesseract_module

    fake_install = tmp_path / "tesseract.exe"
    fake_install.write_bytes(b"")  # existence is all _auto_detect checks

    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        tesseract_module, "_COMMON_WINDOWS_INSTALL_PATHS", [str(fake_install)]
    )
    provider = TesseractOcrProvider()
    assert provider._tesseract_cmd == str(fake_install)


def test_auto_detect_returns_none_when_nothing_found(monkeypatch):
    import ocr.tesseract as tesseract_module

    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        tesseract_module, "_COMMON_WINDOWS_INSTALL_PATHS", [r"C:\does\not\exist.exe"]
    )
    provider = TesseractOcrProvider()
    assert provider._tesseract_cmd is None


def test_not_installed_error_gets_actionable_hint_appended(monkeypatch, tmp_path):
    """The exact failure mode from a real --live run: every image fails OCR
    with pytesseract's 'not installed / not in PATH' error. The message
    should get config.json guidance appended, not just the raw pytesseract
    error, so the fix is discoverable from the log alone."""

    class FakePytesseract:
        class pytesseract:
            tesseract_cmd = ""

        @staticmethod
        def image_to_string(img):
            raise Exception("tesseract is not installed or it's not in your PATH.")

    monkeypatch.setitem(__import__("sys").modules, "pytesseract", FakePytesseract)

    path = tmp_path / "flyer.png"
    Image.new("RGB", (600, 400), "white").save(path)

    provider = TesseractOcrProvider(tesseract_cmd=None)
    result = provider.extract_text(path)

    assert result.success is False
    assert "tesseract_cmd" in result.error
    assert "config.json" in result.error


def test_low_contrast_coloured_flyer_is_recovered(tmp_path):
    """Regression (v11): white text on orange - the fixed threshold-150 pass
    turns BOTH to white and returns an empty string; the fallback recovers it."""
    from PIL import Image, ImageDraw, ImageFont

    if not __import__("shutil").which("tesseract"):
        import pytest
        pytest.skip("tesseract not installed")
    img = Image.new("RGB", (900, 220), (240, 170, 90))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
    except OSError:
        font = ImageFont.load_default()
    d.text((20, 70), "Send CV: hr@acmejobs.com", fill=(255, 255, 255), font=font)
    path = tmp_path / "dark.png"
    img.save(path)
    result = TesseractOcrProvider().extract_text(path)
    assert result.success
    assert "acmejobs.com" in result.text.lower().replace(" ", "")
