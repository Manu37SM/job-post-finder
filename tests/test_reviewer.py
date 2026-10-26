import pytest

from core.models import RecordStatus
from review.reviewer import apply_decision, format_for_review, get_review_queue, run_review_session
from storage.database import Database
from tests.factories import make_record


def test_get_review_queue_only_includes_new(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record(post_url="https://linkedin.com/posts/1", status=RecordStatus.NEW))
    db.upsert(make_record(post_url="https://linkedin.com/posts/2", status=RecordStatus.SKIPPED))
    db.upsert(make_record(post_url="https://linkedin.com/posts/3", status=RecordStatus.APPROVED))

    queue = get_review_queue(db)
    assert [r.extracted.raw.post_url for r in queue] == ["https://linkedin.com/posts/1"]
    db.close()


def test_format_for_review_includes_key_fields():
    record = make_record()
    text = format_for_review(record)
    assert "John Doe" in text
    assert "ABC Technologies" in text
    assert "Java Developer" in text
    assert "Mumbai" in text
    assert "jobs@example.com" in text
    assert "https://linkedin.com/posts/1" in text
    assert "Java Developer detected" in text


def test_format_for_review_handles_unknown_fields():
    record = make_record(company=None, job_role=None, job_location=None, primary_email=None)
    text = format_for_review(record)
    assert "UNKNOWN" in text


def test_apply_decision_approve(tmp_path):
    db = Database(tmp_path / "test.db")
    record = make_record()
    db.upsert(record)
    status = apply_decision(record, "A", db)
    assert status == RecordStatus.APPROVED
    assert db.get_by_post_url(record.extracted.raw.post_url).status == RecordStatus.APPROVED
    db.close()


def test_apply_decision_reject_case_insensitive(tmp_path):
    db = Database(tmp_path / "test.db")
    record = make_record()
    db.upsert(record)
    status = apply_decision(record, "r", db)
    assert status == RecordStatus.REJECTED
    db.close()


def test_apply_decision_skip(tmp_path):
    db = Database(tmp_path / "test.db")
    record = make_record()
    db.upsert(record)
    status = apply_decision(record, "s", db)
    assert status == RecordStatus.SKIPPED
    db.close()


def test_apply_decision_invalid_choice_raises_and_does_not_change_status(tmp_path):
    db = Database(tmp_path / "test.db")
    record = make_record()
    db.upsert(record)
    with pytest.raises(ValueError):
        apply_decision(record, "x", db)
    assert db.get_by_post_url(record.extracted.raw.post_url).status == RecordStatus.NEW
    db.close()


def test_run_review_session_full_flow(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record(post_url="https://linkedin.com/posts/1", status=RecordStatus.NEW))
    db.upsert(make_record(post_url="https://linkedin.com/posts/2", status=RecordStatus.NEW))
    db.upsert(make_record(post_url="https://linkedin.com/posts/3", status=RecordStatus.NEW))

    choices = iter(["A", "R", "S"])
    printed = []
    counts = run_review_session(db, input_fn=lambda _: next(choices), print_fn=printed.append)

    assert counts == {"APPROVED": 1, "REJECTED": 1, "SKIPPED": 1}
    assert db.get_by_post_url("https://linkedin.com/posts/1").status == RecordStatus.APPROVED
    assert db.get_by_post_url("https://linkedin.com/posts/2").status == RecordStatus.REJECTED
    assert db.get_by_post_url("https://linkedin.com/posts/3").status == RecordStatus.SKIPPED
    assert any("Post URL" in line for line in printed)
    db.close()


def test_run_review_session_reprompts_on_invalid_choice(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record(post_url="https://linkedin.com/posts/1", status=RecordStatus.NEW))

    choices = iter(["not-a-choice", "A"])
    printed = []
    counts = run_review_session(db, input_fn=lambda _: next(choices), print_fn=printed.append)

    assert counts == {"APPROVED": 1, "REJECTED": 0, "SKIPPED": 0}
    assert any("Unrecognized review choice" in line for line in printed)
    db.close()


def test_run_review_session_empty_queue(tmp_path):
    db = Database(tmp_path / "test.db")
    counts = run_review_session(db, input_fn=lambda _: "A", print_fn=lambda _: None)
    assert counts == {"APPROVED": 0, "REJECTED": 0, "SKIPPED": 0}
    db.close()
