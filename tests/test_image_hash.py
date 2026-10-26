from PIL import Image, ImageDraw

from ocr.image_hash import compute_phash, hamming_distance, is_near_duplicate
from tests.factories import make_flyer_image
from tests.fonts import bold_font


def test_identical_images_have_zero_distance(tmp_path):
    path1 = make_flyer_image(tmp_path / "a.png", ["Hiring Java Developer", "Mumbai"])
    path2 = make_flyer_image(tmp_path / "b.png", ["Hiring Java Developer", "Mumbai"])

    hash1 = compute_phash(path1)
    hash2 = compute_phash(path2)

    assert hash1 is not None
    assert hash1 == hash2
    assert hamming_distance(hash1, hash2) == 0


def test_recompressed_image_is_a_near_duplicate(tmp_path):
    original_path = make_flyer_image(tmp_path / "orig.png", ["Hiring Java Developer", "Mumbai"])

    # Simulate a "repost" of the same flyer: re-saved as JPEG at a different
    # size, the way a second recruiter downloading and reuploading a flyer
    # image commonly would.
    img = Image.open(original_path).convert("RGB")
    resized = img.resize((300, 200))
    jpeg_path = tmp_path / "repost.jpg"
    resized.save(jpeg_path, "JPEG", quality=80)

    hash1 = compute_phash(original_path)
    hash2 = compute_phash(jpeg_path)

    assert is_near_duplicate(hash1, hash2, max_distance=8)


def test_different_images_are_not_near_duplicates(tmp_path):
    flyer_path = make_flyer_image(tmp_path / "flyer.png", ["Hiring Java Developer", "Mumbai"])

    # A visually distinct image: different background color and content.
    different = Image.new("RGB", (600, 400), "black")
    draw = ImageDraw.Draw(different)
    font = bold_font(32)
    draw.text((30, 200), "Unrelated birthday party invite", fill="white", font=font)
    different_path = tmp_path / "different.png"
    different.save(different_path)

    hash1 = compute_phash(flyer_path)
    hash2 = compute_phash(different_path)

    assert not is_near_duplicate(hash1, hash2, max_distance=8)


def test_compute_phash_missing_file_returns_none(tmp_path):
    assert compute_phash(tmp_path / "does-not-exist.png") is None


def test_compute_phash_corrupt_file_returns_none(tmp_path):
    path = tmp_path / "corrupt.png"
    path.write_bytes(b"not actually a png")
    assert compute_phash(path) is None


def test_is_near_duplicate_respects_threshold(tmp_path):
    hash1 = compute_phash(make_flyer_image(tmp_path / "a.png", ["A"]))
    hash2 = compute_phash(make_flyer_image(tmp_path / "b.png", ["A"]))
    # Identical content -> distance 0, so both a strict and loose threshold pass.
    assert is_near_duplicate(hash1, hash2, max_distance=0)
    assert is_near_duplicate(hash1, hash2, max_distance=8)
