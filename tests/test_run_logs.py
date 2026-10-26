import csv

from storage.run_logs import log_discovery, log_failed, log_ocr_failure, log_skipped, log_success


def test_log_discovery_appends_lines(tmp_path):
    path = tmp_path / "discovery.log"
    log_discovery(path, "Discovered 5 posts")
    log_discovery(path, "Processing post 1")
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert "Discovered 5 posts" in lines[0]


def test_log_success_creates_header_once(tmp_path):
    path = tmp_path / "success.csv"
    log_success(path, "https://linkedin.com/posts/1", "NEW")
    log_success(path, "https://linkedin.com/posts/2", "NEW")

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["post_url"] == "https://linkedin.com/posts/1"
    assert rows[0]["status"] == "NEW"


def test_log_skipped(tmp_path):
    path = tmp_path / "skipped.csv"
    log_skipped(path, "https://linkedin.com/posts/1", "location:UNKNOWN_LOCATION")
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["reason"] == "location:UNKNOWN_LOCATION"


def test_log_failed(tmp_path):
    path = tmp_path / "failed.csv"
    log_failed(path, "https://linkedin.com/posts/1", "boom")
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["error"] == "boom"


def test_log_ocr_failure(tmp_path):
    path = tmp_path / "ocr-failures.csv"
    log_ocr_failure(
        path,
        "https://linkedin.com/posts/1",
        "https://linkedin.com/img/1.png",
        "cannot identify image file",
        "2026-01-01T00:00:00+00:00",
    )
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["image_url"] == "https://linkedin.com/img/1.png"
    assert rows[0]["error"] == "cannot identify image file"
    assert rows[0]["timestamp"] == "2026-01-01T00:00:00+00:00"
