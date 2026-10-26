"""
One definition of "the output schema" shared by excel.py, csv.py and
text.py, so the three formats stay in sync by construction rather than by
remembering to update three places.
"""

import re

from core.models import FilteredRecord

# openpyxl raises IllegalCharacterError on XML-invalid control characters,
# and OCR output regularly contains form-feeds / NULs. One such character
# used to abort the entire Excel export, so strip them from every text cell.
_ILLEGAL_CELL_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_cell(value):
    return _ILLEGAL_CELL_CHARS.sub("", value) if isinstance(value, str) else value

EXPORT_COLUMNS = [
    "post_url",
    "post_date",
    "author_name",
    "author_linkedin",
    "author_headline",
    "company",
    "job_role",
    "role_confidence",
    "job_location",
    "location_confidence",
    "work_mode",
    "email",
    "all_emails",
    "email_source",
    "phone",
    "post_text",
    "ocr_text",
    "source_type",
    "match_reasons",
    "relevance_score",
    "scraped_at",
    "status",
]


def to_export_dict(record: FilteredRecord) -> dict:
    ep = record.extracted
    rp = ep.raw
    return {k: clean_cell(v) for k, v in _raw_export_dict(record, ep, rp).items()}


def _raw_export_dict(record, ep, rp) -> dict:
    return {
        "post_url": rp.post_url,
        "post_date": rp.post_date or "",
        "author_name": rp.author_name or "",
        "author_linkedin": rp.author_linkedin_url or "",
        "author_headline": rp.author_headline or "",
        "company": ep.company or "",
        "job_role": ep.job_role or "",
        "role_confidence": ep.role_confidence.value,
        "job_location": ep.job_location or "",
        "location_confidence": ep.location_confidence.value,
        "work_mode": ep.work_mode.value,
        "email": ep.primary_email or "",
        "all_emails": ", ".join(ep.all_emails),
        "email_source": ep.email_source.value,
        "phone": ep.phone or "",
        "post_text": rp.post_text or "",
        "ocr_text": ep.ocr_text or "",
        "source_type": ep.source_type.value,
        "match_reasons": "; ".join(record.match_reasons),
        "relevance_score": record.relevance_score,
        "scraped_at": rp.scraped_at,
        "status": record.status.value,
    }
