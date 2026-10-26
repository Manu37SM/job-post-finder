from pathlib import Path

from openpyxl import Workbook

from core.models import FilteredRecord
from export.common import EXPORT_COLUMNS, to_export_dict


def export_excel(
    records: list[FilteredRecord], path: str | Path = "data/linkedin_recruiters.xlsx"
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "recruiters"
    ws.append(EXPORT_COLUMNS)

    for record in records:
        row = to_export_dict(record)
        ws.append([row[col] for col in EXPORT_COLUMNS])

    wb.save(path)
    return path
