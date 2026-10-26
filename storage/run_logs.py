"""
Log writers mirroring mass-mailer's success.csv/failed.csv/skipped.csv
convention, extended with discovery.log (plain text) and ocr-failures.csv
per this project's own spec. Every function appends one row/line and
creates the file (with header, for CSVs) on first write.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_csv(path: str | Path, fieldnames: list[str], row: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def log_discovery(path: str | Path, message: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{_now()} {message}\n")


def log_success(path: str | Path, post_url: str, status: str) -> None:
    _append_csv(
        path,
        ["timestamp", "post_url", "status"],
        {"timestamp": _now(), "post_url": post_url, "status": status},
    )


def log_skipped(path: str | Path, post_url: str, reason: str) -> None:
    _append_csv(
        path,
        ["timestamp", "post_url", "reason"],
        {"timestamp": _now(), "post_url": post_url, "reason": reason},
    )


def log_failed(path: str | Path, post_url: str, error: str) -> None:
    _append_csv(
        path,
        ["timestamp", "post_url", "error"],
        {"timestamp": _now(), "post_url": post_url, "error": error},
    )


def log_ocr_failure(
    path: str | Path, post_url: str, image_url: str, error: str, timestamp: str
) -> None:
    _append_csv(
        path,
        ["timestamp", "post_url", "image_url", "error"],
        {"timestamp": timestamp, "post_url": post_url, "image_url": image_url, "error": error},
    )
