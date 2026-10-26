from pathlib import Path

from core.models import FilteredRecord, SourceType

_SOURCE_DISPLAY = {
    SourceType.TEXT: "TEXT",
    SourceType.IMAGE: "IMAGE OCR",
    SourceType.TEXT_IMAGE: "TEXT + IMAGE OCR",
}

_SEPARATOR = "=" * 50


def _format_record(record: FilteredRecord) -> str:
    ep = record.extracted
    rp = ep.raw

    role = ep.job_role or "UNKNOWN"
    location = ep.job_location or "UNKNOWN"
    reasons = "\n".join(f"- {r}" for r in record.match_reasons) or "- (none recorded)"

    return "\n".join(
        [
            _SEPARATOR,
            f"{role} — {location}",
            _SEPARATOR,
            "",
            "Recruiter:",
            rp.author_name or "UNKNOWN",
            "",
            "Company:",
            ep.company or "UNKNOWN",
            "",
            "Email:",
            ep.primary_email or "UNKNOWN",
            "",
            "Location:",
            location,
            "",
            "Work Mode:",
            ep.work_mode.value,
            "",
            "Role:",
            role,
            "",
            "Source:",
            _SOURCE_DISPLAY[ep.source_type],
            "",
            "Match Reasons:",
            reasons,
            "",
            "LinkedIn Post:",
            rp.post_url,
            "",
            _SEPARATOR,
        ]
    )


def export_text(
    records: list[FilteredRecord], path: str | Path = "data/linkedin_recruiters.txt"
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    blocks = [_format_record(r) for r in records]
    content = "\n\n".join(blocks)
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")
    return path
