"""
Shared data shapes passed between pipeline stages.

RawPost      -> what the Playwright layer produces. No interpretation of content.
ExtractedPost -> RawPost + everything derived from text/OCR (email, role, location...).
FilteredRecord -> ExtractedPost + filtering/dedup decisions + review status.

Nothing outside linkedin/ should ever see a Playwright object; nothing outside
storage/ should ever see a sqlite3.Row. Every other module reads and writes
these dataclasses.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SourceType(str, Enum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    TEXT_IMAGE = "TEXT+IMAGE"


class EmailSource(str, Enum):
    POST_TEXT = "POST_TEXT"
    IMAGE_OCR = "IMAGE_OCR"
    BOTH = "BOTH"
    NONE = "NONE"


class WorkMode(str, Enum):
    ONSITE = "ONSITE"
    HYBRID = "HYBRID"
    REMOTE = "REMOTE"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class RecordStatus(str, Enum):
    NEW = "NEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"
    SKIPPED = "SKIPPED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RawPost:
    """Exactly what was scraped. No derived fields. Produced by linkedin/posts.py."""

    post_url: str
    post_text: str
    image_urls: list[str] = field(default_factory=list)
    author_name: str | None = None
    author_linkedin_url: str | None = None
    author_headline: str | None = None
    post_date: str | None = None
    scraped_at: str = field(default_factory=_now_iso)


@dataclass
class ExtractedPost:
    """RawPost plus everything derived from post_text/ocr_text. Pre-filtering."""

    raw: RawPost
    ocr_text: str = ""
    source_type: SourceType = SourceType.TEXT

    company: str | None = None

    job_role: str | None = None
    role_confidence: Confidence = Confidence.NONE

    job_location: str | None = None
    location_confidence: Confidence = Confidence.NONE
    work_mode: WorkMode = WorkMode.UNKNOWN

    all_emails: list[str] = field(default_factory=list)
    primary_email: str | None = None
    email_source: EmailSource = EmailSource.NONE

    phone: str | None = None

    # Perceptual hashes (see ocr/image_hash.py) of images that passed the
    # is_worth_ocr pre-filter - used by filtering/deduplication.py's
    # IMAGE_HASH check to catch the same flyer graphic reposted under a
    # different author/caption/email.
    image_hashes: list[str] = field(default_factory=list)

    @property
    def combined_text(self) -> str:
        """What every text-based extractor/filter should run on."""
        if self.ocr_text:
            return f"{self.raw.post_text}\n{self.ocr_text}"
        return self.raw.post_text


@dataclass
class FilteredRecord:
    """ExtractedPost plus filtering, dedup and review-status decisions."""

    extracted: ExtractedPost

    excluded: bool = False
    exclusion_reason: str | None = None

    location_match: bool = False
    location_match_reason: str | None = None
    location_rejection_reason: str | None = None

    role_match: bool = False

    relevance_score: int = 0
    match_reasons: list[str] = field(default_factory=list)

    duplicate_of: str | None = None
    duplicate_reason: str | None = None

    status: RecordStatus = RecordStatus.NEW
