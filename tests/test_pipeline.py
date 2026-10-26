from config import Config
from core.models import RawPost, RecordStatus, SourceType
from ocr.tesseract import TesseractOcrProvider
from pipeline import process_post
from storage.database import Database
from tests.factories import make_flyer_image

TARGET_ROLES = [
    "Java Developer",
    "Java Engineer",
    "Backend Developer",
    "Spring Boot Developer",
]

EXCLUDE_KEYWORDS = ["course", "bootcamp", "training", "job seeker"]


def _config(**overrides) -> Config:
    defaults = dict(
        target_roles=TARGET_ROLES,
        exclude_keywords=EXCLUDE_KEYWORDS,
        minimum_relevance_score=0,
        deduplicate=True,
    )
    defaults.update(overrides)
    return Config(**defaults)


def test_text_only_mumbai_accepts(tmp_path):
    db = Database(tmp_path / "test.db")
    raw = RawPost(
        post_url="https://linkedin.com/posts/1",
        post_text="Hiring Java Developer\nLocation: Mumbai\nSend CV to jobs@example.com",
        author_name="John Doe",
    )
    record, ocr_failures = process_post(raw, _config(), db)

    assert record.status == RecordStatus.NEW
    assert record.location_match is True
    assert record.role_match is True
    assert record.extracted.primary_email == "jobs@example.com"
    assert record.extracted.source_type == SourceType.TEXT
    assert ocr_failures == []
    db.close()


def test_text_only_pune_rejects(tmp_path):
    db = Database(tmp_path / "test.db")
    raw = RawPost(
        post_url="https://linkedin.com/posts/1",
        post_text="Hiring Java Developer\nLocation: Pune\nSend CV to jobs@example.com",
    )
    record, _ = process_post(raw, _config(), db)

    assert record.status == RecordStatus.SKIPPED
    assert record.location_match is False
    assert record.location_rejection_reason is not None
    db.close()


def test_course_advertisement_excluded(tmp_path):
    db = Database(tmp_path / "test.db")
    raw = RawPost(
        post_url="https://linkedin.com/posts/1",
        post_text="Learn Java Developer skills. Join our Java Bootcamp",
    )
    record, _ = process_post(raw, _config(), db)

    assert record.status == RecordStatus.SKIPPED
    assert record.excluded is True
    assert record.exclusion_reason == "bootcamp"
    db.close()


def test_duplicate_across_two_posts_same_email(tmp_path):
    db = Database(tmp_path / "test.db")
    raw1 = RawPost(
        post_url="https://linkedin.com/posts/1",
        post_text="Hiring Java Developer\nLocation: Mumbai\njobs@example.com",
    )
    record1, _ = process_post(raw1, _config(), db)
    assert record1.status == RecordStatus.NEW
    db.upsert(record1)  # caller's responsibility, per pipeline.py's contract

    raw2 = RawPost(
        post_url="https://linkedin.com/posts/2",
        post_text="Hiring Java Developer\nLocation: Mumbai\njobs@example.com",
    )
    record2, _ = process_post(raw2, _config(), db)

    assert record2.status == RecordStatus.SKIPPED
    assert record2.duplicate_of == "https://linkedin.com/posts/1"
    assert record2.duplicate_reason == "EMAIL"
    db.close()


def test_minimum_relevance_score_gate(tmp_path):
    db = Database(tmp_path / "test.db")
    raw = RawPost(
        post_url="https://linkedin.com/posts/1",
        # Location + role match, but no email/company/hiring-phrase, so the
        # relevance score is low (role + location = 2).
        post_text="Java Developer\nLocation: Mumbai",
    )
    record, _ = process_post(raw, _config(minimum_relevance_score=5), db)

    assert record.status == RecordStatus.SKIPPED
    assert record.location_match is True  # still recorded, just below the bar
    db.close()


def test_image_only_post_via_real_ocr(tmp_path):
    db = Database(tmp_path / "test.db")
    flyer_path = make_flyer_image(
        tmp_path / "flyer.png",
        ["URGENT HIRING", "Java Developer", "Mumbai", "jobs@example.com"],
    )
    raw = RawPost(post_url="https://linkedin.com/posts/1", post_text="")

    record, ocr_failures = process_post(
        raw,
        _config(),
        db,
        image_downloads={"https://linkedin.com/img/1.png": str(flyer_path)},
        ocr_provider=TesseractOcrProvider(),
    )

    assert ocr_failures == []
    assert record.extracted.source_type == SourceType.IMAGE
    assert record.status == RecordStatus.NEW
    assert record.location_match is True
    db.close()


def test_ocr_failure_does_not_crash_pipeline(tmp_path):
    db = Database(tmp_path / "test.db")
    corrupt_path = tmp_path / "corrupt.png"
    corrupt_path.write_bytes(b"not actually a png")

    raw = RawPost(
        post_url="https://linkedin.com/posts/1",
        post_text="Hiring Java Developer - Mumbai - jobs@example.com",
    )
    record, ocr_failures = process_post(
        raw,
        _config(),
        db,
        image_downloads={"https://linkedin.com/img/broken.png": str(corrupt_path)},
        ocr_provider=TesseractOcrProvider(),
    )

    assert len(ocr_failures) == 1
    assert ocr_failures[0].post_url == "https://linkedin.com/posts/1"
    assert ocr_failures[0].image_url == "https://linkedin.com/img/broken.png"
    assert ocr_failures[0].error
    # Post text alone was still enough to process and accept the post.
    assert record.status == RecordStatus.NEW
    db.close()


def test_text_and_image_combine_to_text_image_source_type(tmp_path):
    db = Database(tmp_path / "test.db")
    flyer_path = make_flyer_image(tmp_path / "flyer.png", ["Mumbai"])
    raw = RawPost(
        post_url="https://linkedin.com/posts/1",
        post_text="Hiring Java Developer - jobs@example.com",
    )
    record, _ = process_post(
        raw,
        _config(),
        db,
        image_downloads={"https://linkedin.com/img/1.png": str(flyer_path)},
        ocr_provider=TesseractOcrProvider(),
    )
    assert record.extracted.source_type == SourceType.TEXT_IMAGE
    db.close()


def test_small_icon_image_skipped_by_pre_filter(tmp_path):
    from PIL import Image as PILImage

    db = Database(tmp_path / "test.db")
    icon_path = tmp_path / "icon.png"
    PILImage.new("RGB", (40, 40), "white").save(icon_path)

    raw = RawPost(
        post_url="https://linkedin.com/posts/1",
        post_text="Hiring Java Developer - Mumbai - jobs@example.com",
    )
    record, ocr_failures = process_post(
        raw,
        _config(),
        db,
        image_downloads={"https://linkedin.com/img/icon.png": str(icon_path)},
        ocr_provider=TesseractOcrProvider(),
    )
    # Pre-filter should have skipped OCR entirely - no failure logged, no
    # OCR text merged in, source_type stays TEXT.
    assert ocr_failures == []
    assert record.extracted.ocr_text == ""
    assert record.extracted.source_type == SourceType.TEXT
    db.close()


def test_reposted_flyer_deduped_via_image_hash_end_to_end(tmp_path):
    from PIL import Image

    db = Database(tmp_path / "test.db")

    original = make_flyer_image(
        tmp_path / "orig.png", ["Hiring Java Developer", "Mumbai"]
    )
    reposted = tmp_path / "reposted.jpg"
    Image.open(original).convert("RGB").resize((300, 200)).save(reposted, "JPEG", quality=80)

    raw1 = RawPost(post_url="https://linkedin.com/posts/1", post_text="")
    record1, _ = process_post(
        raw1,
        _config(),
        db,
        image_downloads={"https://linkedin.com/img/1.png": str(original)},
        ocr_provider=TesseractOcrProvider(),
    )
    assert record1.status == RecordStatus.NEW
    db.upsert(record1)

    # Same flyer, different author, no OCR-visible text overlap in caption -
    # the only thing tying these together is the graphic itself.
    raw2 = RawPost(
        post_url="https://linkedin.com/posts/2",
        post_text="",
        author_name="A Different Recruiter",
    )
    record2, _ = process_post(
        raw2,
        _config(),
        db,
        image_downloads={"https://linkedin.com/img/2.jpg": str(reposted)},
        ocr_provider=TesseractOcrProvider(),
    )

    assert record2.status == RecordStatus.SKIPPED
    assert record2.duplicate_of == "https://linkedin.com/posts/1"
    assert record2.duplicate_reason == "IMAGE_HASH"
    db.close()
