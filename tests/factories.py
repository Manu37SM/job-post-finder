"""
Not a test module itself (no test_ prefix, won't be collected) - just shared
builders so test_storage.py / test_deduplication.py / test_export.py /
test_pipeline.py don't each hand-roll fixtures.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from core.models import (
    Confidence,
    EmailSource,
    ExtractedPost,
    FilteredRecord,
    RawPost,
    RecordStatus,
    SourceType,
    WorkMode,
)

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def make_flyer_image(path: Path, lines: list[str], size=(600, 400)) -> Path:
    """Synthetic 'hiring poster' image for OCR-integration tests."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(_FONT_PATH, 32)
    y = 30
    for line in lines:
        draw.text((30, y), line, fill="black", font=font)
        y += 50
    img.save(path)
    return path


# ---- Minimal duck-typed fakes for Playwright's Locator/Page API, used only
# to test linkedin/posts.py and linkedin/search.py's parsing logic without a
# real browser. Cover just the handful of methods those modules call.


class FakePostElement:
    """
    Stands in for a Playwright Locator representing one post container.
    linkedin/posts.py's parse_post_element() now extracts via
    el.evaluate(js) (see that module's docstring for why: DOM tree-walking
    is far cleaner in JS than chained Python Locator calls) - so this fake
    just returns a preset dict from evaluate(), or raises if configured to,
    rather than simulating individual .locator() calls. The actual
    extraction JS itself is validated separately against real captured
    LinkedIn HTML via Node+jsdom (see linkedin/posts.py's docstring) - these
    Python tests only cover parse_post_element()'s wrapper behavior
    (None-handling, exception safety), not the JS logic itself.
    """

    def __init__(self, evaluate_result: dict | None = None, raise_on_evaluate=False):
        self._evaluate_result = evaluate_result
        self._raise_on_evaluate = raise_on_evaluate

    def evaluate(self, js: str):
        if self._raise_on_evaluate:
            raise RuntimeError("simulated Playwright evaluate() error")
        return self._evaluate_result


def make_fake_post_element(post_url: str, post_text: str = "", image_srcs=None) -> FakePostElement:
    """Convenience builder mimicking a successful parse_post_element() JS
    evaluation - used by test_linkedin_search.py to simulate scroll batches."""
    return FakePostElement(
        evaluate_result={
            "post_url": post_url,
            "post_text": post_text,
            "image_urls": image_srcs or [],
            "author_name": None,
            "author_linkedin_url": None,
            "author_headline": None,
            "post_date": None,
        }
    )


def make_record(
    post_url="https://linkedin.com/posts/1",
    post_text="Hiring Java Developer - Mumbai",
    author_name="John Doe",
    author_linkedin_url="https://linkedin.com/in/johndoe",
    company="ABC Technologies",
    job_role="Java Developer",
    job_location="Mumbai",
    work_mode=WorkMode.ONSITE,
    primary_email="jobs@example.com",
    all_emails=None,
    match_reasons=None,
    status=RecordStatus.NEW,
    location_match=True,
    role_match=True,
) -> FilteredRecord:
    raw = RawPost(
        post_url=post_url,
        post_text=post_text,
        author_name=author_name,
        author_linkedin_url=author_linkedin_url,
    )
    extracted = ExtractedPost(
        raw=raw,
        source_type=SourceType.TEXT,
        company=company,
        job_role=job_role,
        role_confidence=Confidence.HIGH,
        job_location=job_location,
        location_confidence=Confidence.HIGH,
        work_mode=work_mode,
        all_emails=all_emails if all_emails is not None else (
            [primary_email] if primary_email else []
        ),
        primary_email=primary_email,
        email_source=EmailSource.POST_TEXT if primary_email else EmailSource.NONE,
    )
    return FilteredRecord(
        extracted=extracted,
        location_match=location_match,
        role_match=role_match,
        relevance_score=3,
        match_reasons=match_reasons
        if match_reasons is not None
        else ["Java Developer detected", "Mumbai detected"],
        status=status,
    )
