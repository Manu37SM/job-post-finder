"""
CLI human-review step. Only status == NEW records are queued - SKIPPED
records already failed an automatic filter in pipeline.py and don't need a
human to look at them; APPROVED/REJECTED/SENT are already decided.

input_fn/print_fn are injectable so run_review_session is testable without
real stdin/stdout (see tests/test_reviewer.py) - this mirrors how the
mass-mailer GUI's Run tab drives app.py's logic without a terminal.
"""

from core.models import FilteredRecord, RecordStatus
from storage.database import Database

_CHOICE_TO_STATUS = {
    "a": RecordStatus.APPROVED,
    "r": RecordStatus.REJECTED,
    "s": RecordStatus.SKIPPED,
}


def get_review_queue(db: Database) -> list[FilteredRecord]:
    return [r for r in db.all_records() if r.status == RecordStatus.NEW]


def format_for_review(record: FilteredRecord) -> str:
    ep = record.extracted
    rp = ep.raw
    reasons = [f"  - {r}" for r in record.match_reasons] or ["  - (none recorded)"]
    return "\n".join(
        [
            f"Name:      {rp.author_name or 'UNKNOWN'}",
            f"Company:   {ep.company or 'UNKNOWN'}",
            f"Role:      {ep.job_role or 'UNKNOWN'}",
            f"Location:  {ep.job_location or 'UNKNOWN'}",
            f"Work Mode: {ep.work_mode.value}",
            f"Email:     {ep.primary_email or 'UNKNOWN'}",
            f"Post URL:  {rp.post_url}",
            "Why it matched:",
            *reasons,
        ]
    )


def apply_decision(record: FilteredRecord, choice: str, db: Database) -> RecordStatus:
    """
    choice is 'a'/'r'/'s', case-insensitive. Updates the DB and returns the
    resulting status. Raises ValueError on an unrecognized choice - the
    caller is responsible for re-prompting rather than silently defaulting.
    """
    key = choice.strip().lower()
    if key not in _CHOICE_TO_STATUS:
        raise ValueError(f"Unrecognized review choice: {choice!r} (expected A/R/S)")
    new_status = _CHOICE_TO_STATUS[key]
    db.update_status(record.extracted.raw.post_url, new_status)
    return new_status


def run_review_session(db: Database, input_fn=input, print_fn=print) -> dict[str, int]:
    """Interactive loop over the review queue. Returns final decision counts."""
    queue = get_review_queue(db)
    counts = {"APPROVED": 0, "REJECTED": 0, "SKIPPED": 0}

    for i, record in enumerate(queue, start=1):
        print_fn(f"\n[{i}/{len(queue)}]")
        print_fn(format_for_review(record))
        while True:
            choice = input_fn("Approve / Reject / Skip? [A/R/S]: ")
            try:
                status = apply_decision(record, choice, db)
                break
            except ValueError as e:
                print_fn(str(e))
        counts[status.value] += 1

    return counts
