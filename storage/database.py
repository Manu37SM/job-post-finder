"""
SQLite storage for FilteredRecord data.

One denormalized `records` table rather than the posts/contacts/extractions/
reviews/processing_log split the spec mentioned as a possibility: for a
single-user tool the join overhead of five tables buys nothing (every field
already lives together as one FilteredRecord in memory, and there's no
multi-user or relational-reporting need to justify normalizing it). Indexed
on the three dedup lookup columns that matter (email, author URL, status);
post_url is the primary key so exact-post-url dedup is free.

If this ever needs to become multi-table (e.g. tracking OCR attempts per
image separately), that's a schema migration, not a rewrite of this module's
public interface (upsert/get_by_post_url/find_by_email/...).
"""

import json
import sqlite3
from pathlib import Path

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

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    post_url TEXT PRIMARY KEY,
    post_text TEXT,
    image_urls TEXT,
    author_name TEXT,
    author_linkedin_url TEXT,
    author_headline TEXT,
    post_date TEXT,
    scraped_at TEXT,

    ocr_text TEXT,
    source_type TEXT,

    company TEXT,
    job_role TEXT,
    role_confidence TEXT,

    job_location TEXT,
    location_confidence TEXT,
    work_mode TEXT,

    all_emails TEXT,
    primary_email TEXT,
    email_source TEXT,
    phone TEXT,
    image_hashes TEXT,

    excluded INTEGER,
    exclusion_reason TEXT,

    location_match INTEGER,
    location_match_reason TEXT,
    location_rejection_reason TEXT,

    role_match INTEGER,

    relevance_score INTEGER,
    match_reasons TEXT,

    duplicate_of TEXT,
    duplicate_reason TEXT,

    status TEXT
);

CREATE INDEX IF NOT EXISTS idx_records_primary_email ON records(primary_email);
CREATE INDEX IF NOT EXISTS idx_records_author_url ON records(author_linkedin_url);
CREATE INDEX IF NOT EXISTS idx_records_status ON records(status);
"""

_COLUMNS = [
    "post_url", "post_text", "image_urls", "author_name", "author_linkedin_url",
    "author_headline", "post_date", "scraped_at", "ocr_text", "source_type",
    "company", "job_role", "role_confidence", "job_location", "location_confidence",
    "work_mode", "all_emails", "primary_email", "email_source", "phone",
    "image_hashes",
    "excluded", "exclusion_reason", "location_match", "location_match_reason",
    "location_rejection_reason",
    "role_match", "relevance_score", "match_reasons", "duplicate_of",
    "duplicate_reason", "status",
]


class Database:
    def __init__(self, path: str | Path = "data/linkedin_recruiters.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the Tkinter GUI (gui.py) runs a pipeline
        # via GuiController on a background worker thread, then the main
        # thread reads/updates the same Database instance afterward (Review
        # tab, Export tab) - both real uses, never simultaneous, but on
        # different threads. Safe here because this project never writes
        # from two threads at once; if that ever changes, this needs a lock
        # or a per-thread connection instead of just disabling the guard.
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self) -> None:
        # Python 3.13 emits a ResourceWarning for an unclosed sqlite3
        # connection; closing here keeps `pytest -W error` (and CI) clean
        # without every caller having to remember close().
        try:
            self.conn.close()
        except Exception:  # noqa: BLE001 - interpreter shutdown / half-built object
            pass

    def upsert(self, record: FilteredRecord) -> None:
        row = _record_to_row(record)
        columns = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        updates = ", ".join(f"{k}=excluded.{k}" for k in row if k != "post_url")
        self.conn.execute(
            f"INSERT INTO records ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(post_url) DO UPDATE SET {updates}",
            list(row.values()),
        )
        self.conn.commit()

    def get_by_post_url(self, post_url: str) -> FilteredRecord | None:
        row = self.conn.execute(
            "SELECT * FROM records WHERE post_url = ?", (post_url,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def find_by_email(self, email: str) -> FilteredRecord | None:
        row = self.conn.execute(
            "SELECT * FROM records WHERE primary_email = ? LIMIT 1", (email,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def find_all_by_email(self, email: str) -> list[FilteredRecord]:
        rows = self.conn.execute(
            "SELECT * FROM records WHERE primary_email = ?", (email,)
        ).fetchall()
        return [_row_to_record(r) for r in rows]

    def find_by_author_url(self, author_linkedin_url: str) -> list[FilteredRecord]:
        rows = self.conn.execute(
            "SELECT * FROM records WHERE author_linkedin_url = ?", (author_linkedin_url,)
        ).fetchall()
        return [_row_to_record(r) for r in rows]

    def all_records(self) -> list[FilteredRecord]:
        rows = self.conn.execute("SELECT * FROM records").fetchall()
        return [_row_to_record(r) for r in rows]

    def update_status(self, post_url: str, status: RecordStatus) -> None:
        self.conn.execute(
            "UPDATE records SET status = ? WHERE post_url = ?",
            (status.value, post_url),
        )
        self.conn.commit()

    def seen_post_urls(self) -> set[str]:
        """For checkpoint/resume: post_urls already processed in a prior run."""
        rows = self.conn.execute("SELECT post_url FROM records").fetchall()
        return {r[0] for r in rows}


def _record_to_row(record: FilteredRecord) -> dict:
    ep = record.extracted
    rp = ep.raw
    return {
        "post_url": rp.post_url,
        "post_text": rp.post_text,
        "image_urls": json.dumps(rp.image_urls),
        "author_name": rp.author_name,
        "author_linkedin_url": rp.author_linkedin_url,
        "author_headline": rp.author_headline,
        "post_date": rp.post_date,
        "scraped_at": rp.scraped_at,
        "ocr_text": ep.ocr_text,
        "source_type": ep.source_type.value,
        "company": ep.company,
        "job_role": ep.job_role,
        "role_confidence": ep.role_confidence.value,
        "job_location": ep.job_location,
        "location_confidence": ep.location_confidence.value,
        "work_mode": ep.work_mode.value,
        "all_emails": json.dumps(ep.all_emails),
        "primary_email": ep.primary_email,
        "email_source": ep.email_source.value,
        "phone": ep.phone,
        "image_hashes": json.dumps(ep.image_hashes),
        "excluded": int(record.excluded),
        "exclusion_reason": record.exclusion_reason,
        "location_match": int(record.location_match),
        "location_match_reason": record.location_match_reason,
        "location_rejection_reason": record.location_rejection_reason,
        "role_match": int(record.role_match),
        "relevance_score": record.relevance_score,
        "match_reasons": json.dumps(record.match_reasons),
        "duplicate_of": record.duplicate_of,
        "duplicate_reason": record.duplicate_reason,
        "status": record.status.value,
    }


def _row_to_record(row: sqlite3.Row) -> FilteredRecord:
    raw = RawPost(
        post_url=row["post_url"],
        post_text=row["post_text"] or "",
        image_urls=json.loads(row["image_urls"] or "[]"),
        author_name=row["author_name"],
        author_linkedin_url=row["author_linkedin_url"],
        author_headline=row["author_headline"],
        post_date=row["post_date"],
        scraped_at=row["scraped_at"],
    )
    extracted = ExtractedPost(
        raw=raw,
        ocr_text=row["ocr_text"] or "",
        source_type=SourceType(row["source_type"]),
        company=row["company"],
        job_role=row["job_role"],
        role_confidence=Confidence(row["role_confidence"]),
        job_location=row["job_location"],
        location_confidence=Confidence(row["location_confidence"]),
        work_mode=WorkMode(row["work_mode"]),
        all_emails=json.loads(row["all_emails"] or "[]"),
        primary_email=row["primary_email"],
        email_source=EmailSource(row["email_source"]),
        phone=row["phone"],
        image_hashes=json.loads(row["image_hashes"] or "[]"),
    )
    return FilteredRecord(
        extracted=extracted,
        excluded=bool(row["excluded"]),
        exclusion_reason=row["exclusion_reason"],
        location_match=bool(row["location_match"]),
        location_match_reason=row["location_match_reason"],
        location_rejection_reason=row["location_rejection_reason"],
        role_match=bool(row["role_match"]),
        relevance_score=row["relevance_score"],
        match_reasons=json.loads(row["match_reasons"] or "[]"),
        duplicate_of=row["duplicate_of"],
        duplicate_reason=row["duplicate_reason"],
        status=RecordStatus(row["status"]),
    )
