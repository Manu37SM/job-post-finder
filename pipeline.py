"""
Wires everything built so far into one function: RawPost -> FilteredRecord.
This is the only place that knows the *order* filters run in; every
individual extractor/filter stays independently testable without knowing
about this ordering.

Status assignment (not fully spelled out in the spec, documenting the
decision explicitly here): every RawPost produces a FilteredRecord - nothing
is silently dropped, because dedup needs to see rejected posts too (a
recruiter reposting a since-rejected job is still worth recognizing as a
repost, and you asked for full diagnostics either way).

  - excluded (false-positive keyword)      -> status SKIPPED
  - location filter fails                  -> status SKIPPED
  - below config.minimum_relevance_score   -> status SKIPPED
  - duplicate of an already-stored record  -> status SKIPPED
  - otherwise                              -> status NEW (ready for human review)

APPROVED/REJECTED are reserved for the human review step (review/reviewer.py,
not built yet) - the pipeline itself never assigns them; SKIPPED here means
"the pipeline decided this doesn't qualify," not "a human skipped it."

process_post does NOT write to the database itself - it only reads from `db`
for dedup lookups. The caller (app.py, not built yet) is responsible for
`db.upsert(record)` after each call, including for SKIPPED records, so later
posts in the same run can be deduped against earlier ones.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from config import Config
from core.models import ExtractedPost, FilteredRecord, RawPost, RecordStatus, SourceType
from extraction.email_extractor import extract_emails
from extraction.location_extractor import extract_location, extract_work_mode
from extraction.recruiter_extractor import detect_hiring_signal, extract_company
from extraction.role_extractor import extract_role
from filtering.deduplication import find_duplicate
from filtering.exclusions import check_exclusion
from filtering.location import location_decision
from filtering.relevance import compute_relevance
from filtering.role import role_matches
from ocr.engine import OcrProvider, is_worth_ocr
from ocr.image_hash import compute_phash
from storage.database import Database


@dataclass
class OcrFailure:
    post_url: str
    image_url: str
    error: str
    timestamp: str


def process_post(
    raw: RawPost,
    config: Config,
    db: Database,
    image_downloads: dict[str, str] | None = None,
    ocr_provider: OcrProvider | None = None,
) -> tuple[FilteredRecord, list[OcrFailure]]:
    """
    image_downloads maps image_url -> local file path (produced by the
    not-yet-built linkedin/images.py). Pass None/{} for a text-only post or
    when testing without real images - OCR is simply skipped in that case.
    """
    ocr_texts: list[str] = []
    ocr_failures: list[OcrFailure] = []
    image_hashes: list[str] = []

    if image_downloads and ocr_provider is not None:
        for image_url, local_path in image_downloads.items():
            if not is_worth_ocr(local_path):
                continue

            image_hash = compute_phash(local_path)
            if image_hash is not None:
                image_hashes.append(image_hash)

            result = ocr_provider.extract_text(local_path)
            if result.success and result.text:
                ocr_texts.append(result.text)
            elif not result.success:
                ocr_failures.append(
                    OcrFailure(
                        post_url=raw.post_url,
                        image_url=image_url,
                        error=result.error or "unknown OCR error",
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                )

    ocr_text = "\n".join(t for t in ocr_texts if t)
    has_text = bool(raw.post_text.strip())
    has_ocr = bool(ocr_text.strip())

    if has_text and has_ocr:
        source_type = SourceType.TEXT_IMAGE
    elif has_ocr:
        source_type = SourceType.IMAGE
    else:
        source_type = SourceType.TEXT

    combined_text = f"{raw.post_text}\n{ocr_text}" if has_ocr else raw.post_text

    all_emails, primary_email, email_source = extract_emails(raw.post_text, ocr_text)
    job_role, role_confidence = extract_role(combined_text, config.target_roles)
    job_location, location_confidence = extract_location(combined_text)
    work_mode = extract_work_mode(combined_text, config.accepted_remote_terms)
    company = extract_company(combined_text)
    hiring_signal = detect_hiring_signal(combined_text)

    extracted = ExtractedPost(
        raw=raw,
        ocr_text=ocr_text,
        source_type=source_type,
        company=company,
        job_role=job_role,
        role_confidence=role_confidence,
        job_location=job_location,
        location_confidence=location_confidence,
        work_mode=work_mode,
        all_emails=all_emails,
        primary_email=primary_email,
        email_source=email_source,
        image_hashes=image_hashes,
    )

    excluded, exclusion_reason = check_exclusion(combined_text, config.exclude_keywords)
    record = FilteredRecord(
        extracted=extracted, excluded=excluded, exclusion_reason=exclusion_reason
    )

    if excluded:
        record.status = RecordStatus.SKIPPED
        return record, ocr_failures

    location_match, location_reason = location_decision(
        job_location, work_mode, config.accepted_location_aliases
    )
    record.location_match = location_match
    record.location_match_reason = location_reason
    record.location_rejection_reason = None if location_match else location_reason

    if not location_match:
        record.status = RecordStatus.SKIPPED
        return record, ocr_failures

    record.role_match = role_matches(role_confidence)

    score, reasons = compute_relevance(
        extracted, location_match, record.role_match, hiring_signal
    )
    record.relevance_score = score
    record.match_reasons = reasons

    if score < config.minimum_relevance_score:
        record.status = RecordStatus.SKIPPED
        return record, ocr_failures

    if config.deduplicate:
        dup_of, dup_reason = find_duplicate(
            record, db, image_hash_max_distance=config.image_hash_max_distance
        )
        if dup_of:
            record.duplicate_of = dup_of
            record.duplicate_reason = dup_reason
            record.status = RecordStatus.SKIPPED
            return record, ocr_failures

    record.status = RecordStatus.NEW
    return record, ocr_failures
