import csv
from pathlib import Path

from core.models import FilteredRecord
from export.common import EXPORT_COLUMNS, to_export_dict


def export_csv(
    records: list[FilteredRecord], path: str | Path = "data/linkedin_recruiters.csv"
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM: Excel shows non-ASCII names correctly
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(to_export_dict(record))

    return path
