"""
Adapter layer between this project and the existing mass-mailer:
data/approved_recruiters.xlsx, in the exact schema mass-mailer/parser.py
reads (Name, Email, Company, Title - case-sensitive headers, confirmed from
the uploaded mass-mailer source).

Only status == APPROVED records are exported - this is the deliberate gate
between discovery and the existing mailer ("Do NOT combine scraping and
email sending into one uncontrolled process" - spec). Nothing here writes
to mass-mailer's own files or touches its code.
"""

from pathlib import Path

from openpyxl import Workbook

from core.models import FilteredRecord, RecordStatus
from export.common import clean_cell

MAILER_COLUMNS = ["Name", "Email", "Company", "Title"]


def to_mailer_rows(records: list[FilteredRecord]) -> list[dict]:
    rows = []
    seen_emails: set[str] = set()
    for record in records:
        if record.status != RecordStatus.APPROVED:
            continue
        ep = record.extracted
        if not ep.primary_email:
            # mass-mailer's own parser drops rows with no email anyway -
            # skip here so this export doesn't carry rows that would
            # silently vanish on the mailer side.
            continue
        key = ep.primary_email.strip().lower()
        if key in seen_emails:
            # The same recruiter approved from two posts must not be mailed twice.
            continue
        seen_emails.add(key)
        rows.append(
            {
                "Name": clean_cell(ep.raw.author_name or ""),
                "Email": ep.primary_email,
                "Company": clean_cell(ep.company or ""),
                "Title": clean_cell(ep.job_role or ""),
            }
        )
    return rows


def export_approved_for_mailer(
    records: list[FilteredRecord], path: str | Path = "data/approved_recruiters.xlsx"
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "recruiters"
    ws.append(MAILER_COLUMNS)
    for row in to_mailer_rows(records):
        ws.append([row[col] for col in MAILER_COLUMNS])

    wb.save(path)
    return path
