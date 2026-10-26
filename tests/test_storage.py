from core.models import Confidence, EmailSource, RecordStatus, WorkMode
from storage.database import Database
from tests.factories import make_record


def test_upsert_and_get_roundtrip(tmp_path):
    db = Database(tmp_path / "test.db")
    record = make_record()
    db.upsert(record)

    fetched = db.get_by_post_url(record.extracted.raw.post_url)
    assert fetched is not None
    assert fetched.extracted.raw.post_url == record.extracted.raw.post_url
    assert fetched.extracted.company == "ABC Technologies"
    assert fetched.extracted.job_role == "Java Developer"
    assert fetched.extracted.role_confidence == Confidence.HIGH
    assert fetched.extracted.work_mode == WorkMode.ONSITE
    assert fetched.extracted.primary_email == "jobs@example.com"
    assert fetched.extracted.all_emails == ["jobs@example.com"]
    assert fetched.extracted.email_source == EmailSource.POST_TEXT
    assert fetched.match_reasons == ["Java Developer detected", "Mumbai detected"]
    assert fetched.status == RecordStatus.NEW
    db.close()


def test_upsert_is_idempotent_on_post_url(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record())
    db.upsert(make_record())
    assert len(db.all_records()) == 1
    db.close()


def test_upsert_overwrites_on_conflict(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record(company="ABC Technologies"))
    db.upsert(make_record(company="Updated Co"))
    fetched = db.get_by_post_url("https://linkedin.com/posts/1")
    assert fetched.extracted.company == "Updated Co"
    db.close()


def test_update_status(tmp_path):
    db = Database(tmp_path / "test.db")
    record = make_record()
    db.upsert(record)
    db.update_status(record.extracted.raw.post_url, RecordStatus.APPROVED)
    fetched = db.get_by_post_url(record.extracted.raw.post_url)
    assert fetched.status == RecordStatus.APPROVED
    db.close()


def test_get_by_post_url_missing_returns_none(tmp_path):
    db = Database(tmp_path / "test.db")
    assert db.get_by_post_url("https://linkedin.com/posts/none") is None
    db.close()


def test_find_by_email(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record(post_url="https://linkedin.com/posts/1", primary_email="jobs@example.com"))
    found = db.find_by_email("jobs@example.com")
    assert found is not None
    assert found.extracted.raw.post_url == "https://linkedin.com/posts/1"
    db.close()


def test_find_by_email_no_match(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record())
    assert db.find_by_email("nobody@example.com") is None
    db.close()


def test_find_by_author_url(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record(post_url="https://linkedin.com/posts/1"))
    db.upsert(make_record(post_url="https://linkedin.com/posts/2"))
    matches = db.find_by_author_url("https://linkedin.com/in/johndoe")
    assert len(matches) == 2
    db.close()


def test_seen_post_urls(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record(post_url="https://linkedin.com/posts/1"))
    db.upsert(make_record(post_url="https://linkedin.com/posts/2"))
    assert db.seen_post_urls() == {
        "https://linkedin.com/posts/1",
        "https://linkedin.com/posts/2",
    }
    db.close()


def test_all_records_empty_db(tmp_path):
    db = Database(tmp_path / "test.db")
    assert db.all_records() == []
    db.close()
