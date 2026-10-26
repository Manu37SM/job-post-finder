"""
Checks a new FilteredRecord against already-stored records, in priority
order:

  1. exact post_url
  2. normalized primary_email
  3. author_linkedin_url + same (company, role, location)
  4. author_linkedin_url + similar post_text prefix (no job metadata needed)
  5. normalized (company, role, location) regardless of author
  6. perceptual image hash near-match (see ocr/image_hash.py) - catches the
     same flyer graphic reposted under a different author, caption text and
     contact email, which the text-based checks all miss since every one of
     them depends on text that changed between reposts.

First match wins. A non-match is NOT discarded here - the caller stores it
either way; this function only reports what to record in
duplicate_of/duplicate_reason (see core/models.FilteredRecord).

Rule 4 added after a real case: the same post, with no company/role
extracted (so rule 3's _same_job() can't engage at all - it requires all
three fields truthy), appeared twice in one run under two different
synthetic post_urls (see linkedin/posts.py - a synthetic post_url is built
from a post-text slice, which can drift slightly if the same post renders
under two different search terms within a run). author_linkedin_url comes
from a stable profile href, independent of any post-text variability, so
it's the right anchor for this check even when post_url itself isn't
trustworthy. Requiring a shared text prefix (not just the same author)
keeps this from falsely merging two genuinely different jobs the same
recruiter posted separately.

Rule 6 was originally deferred out of MVP as a narrow case not worth the
extra dependency (imagehash) until the text-based rules were proven. Built
on request - additive, nothing above this module changed except
pipeline.py now also computes and passes image_hashes.
"""

from core.models import ExtractedPost, FilteredRecord, RecordStatus
from ocr.image_hash import is_near_duplicate
from storage.database import Database

# How many leading characters of normalized post_text must match for two
# same-author records to count as the same post absent any job metadata.
# Long enough to avoid matching on a generic opener ("Hiring Java
# Developer" alone), short enough to tolerate a trailing-content difference
# from the exact rendering quirk that causes this in the first place.
_SAME_TEXT_PREFIX_LENGTH = 60


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").split()).lower()


def _same_job(a: ExtractedPost, b: ExtractedPost) -> bool:
    if not (a.company and a.job_role and a.job_location):
        return False
    return (
        _normalize(a.company) == _normalize(b.company)
        and _normalize(a.job_role) == _normalize(b.job_role)
        and _normalize(a.job_location) == _normalize(b.job_location)
    )


def _same_author_similar_text(a: ExtractedPost, b: ExtractedPost) -> bool:
    prefix_a = _normalize_text(a.raw.post_text)[:_SAME_TEXT_PREFIX_LENGTH]
    prefix_b = _normalize_text(b.raw.post_text)[:_SAME_TEXT_PREFIX_LENGTH]
    return bool(prefix_a) and prefix_a == prefix_b


def _shares_near_duplicate_image(
    a: ExtractedPost, b: ExtractedPost, max_distance: int
) -> bool:
    if not a.image_hashes or not b.image_hashes:
        return False
    return any(
        is_near_duplicate(hash_a, hash_b, max_distance)
        for hash_a in a.image_hashes
        for hash_b in b.image_hashes
    )


def _is_live(candidate: FilteredRecord) -> bool:
    """
    Only records that survived filtering can make a new post a duplicate.

    Bug fixed in v11: a SKIPPED record (rejected for location, excluded
    keyword, or low relevance) used to count as a duplicate target, so a
    recruiter's Mumbai job was dropped as "EMAIL duplicate" of their earlier
    Pune post - silently losing a valid email. Exact POST_URL matches still
    short-circuit against every status (that post was already processed).
    """
    return candidate.status in (
        RecordStatus.NEW, RecordStatus.APPROVED, RecordStatus.REJECTED
    )


def find_duplicate(
    record: FilteredRecord, db: Database, image_hash_max_distance: int = 8
) -> tuple[str | None, str | None]:
    """Returns (duplicate_of_post_url, reason), or (None, None) if no duplicate found."""
    ep = record.extracted
    post_url = ep.raw.post_url

    existing = db.get_by_post_url(post_url)
    if existing is not None:
        return existing.extracted.raw.post_url, "POST_URL"

    if ep.primary_email:
        for match in db.find_all_by_email(ep.primary_email):
            if _is_live(match) and match.extracted.raw.post_url != post_url:
                return match.extracted.raw.post_url, "EMAIL"

    if ep.raw.author_linkedin_url:
        for candidate in db.find_by_author_url(ep.raw.author_linkedin_url):
            if candidate.extracted.raw.post_url == post_url or not _is_live(candidate):
                continue
            if _same_job(candidate.extracted, ep):
                return candidate.extracted.raw.post_url, "AUTHOR_SAME_JOB"
            if _same_author_similar_text(candidate.extracted, ep):
                return candidate.extracted.raw.post_url, "AUTHOR_SAME_TEXT"

    # Fallback scan: fine at personal-use scale (hundreds/low-thousands of
    # rows). Revisit with an indexed hash column if this ever needs to scale
    # further. Checks both remaining rules per candidate in one pass rather
    # than scanning the table twice.
    for candidate in db.all_records():
        if candidate.extracted.raw.post_url == post_url or not _is_live(candidate):
            continue
        if _same_job(candidate.extracted, ep):
            return candidate.extracted.raw.post_url, "COMPANY_ROLE_LOCATION"
        if _shares_near_duplicate_image(candidate.extracted, ep, image_hash_max_distance):
            return candidate.extracted.raw.post_url, "IMAGE_HASH"

    return None, None
