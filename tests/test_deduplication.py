from core.models import RecordStatus
from filtering.deduplication import find_duplicate
from storage.database import Database
from tests.factories import make_record


def test_no_duplicate_on_empty_db(tmp_path):
    db = Database(tmp_path / "test.db")
    dup_of, reason = find_duplicate(make_record(), db)
    assert dup_of is None
    assert reason is None
    db.close()


def test_exact_post_url_duplicate(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record(post_url="https://linkedin.com/posts/1"))

    new_record = make_record(post_url="https://linkedin.com/posts/1", company="Different Co")
    dup_of, reason = find_duplicate(new_record, db)
    assert dup_of == "https://linkedin.com/posts/1"
    assert reason == "POST_URL"
    db.close()


def test_email_duplicate(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(make_record(post_url="https://linkedin.com/posts/1", primary_email="jobs@example.com"))

    new_record = make_record(post_url="https://linkedin.com/posts/2", primary_email="jobs@example.com")
    dup_of, reason = find_duplicate(new_record, db)
    assert dup_of == "https://linkedin.com/posts/1"
    assert reason == "EMAIL"
    db.close()


def test_author_same_job_duplicate(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(
        make_record(
            post_url="https://linkedin.com/posts/1",
            author_linkedin_url="https://linkedin.com/in/johndoe",
            primary_email="jobs@example.com",
            company="ABC Technologies",
            job_role="Java Developer",
            job_location="Mumbai",
        )
    )

    # Same author reposting the same job under a different contact email -
    # the email check won't catch this; the author+same-job check should.
    new_record = make_record(
        post_url="https://linkedin.com/posts/2",
        author_linkedin_url="https://linkedin.com/in/johndoe",
        primary_email="hr@example.com",
        company="ABC Technologies",
        job_role="Java Developer",
        job_location="Mumbai",
    )
    dup_of, reason = find_duplicate(new_record, db)
    assert dup_of == "https://linkedin.com/posts/1"
    assert reason == "AUTHOR_SAME_JOB"
    db.close()


def test_company_role_location_duplicate_different_author(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(
        make_record(
            post_url="https://linkedin.com/posts/1",
            author_linkedin_url="https://linkedin.com/in/johndoe",
            primary_email="jobs@example.com",
            company="ABC Technologies",
            job_role="Java Developer",
            job_location="Mumbai",
        )
    )

    new_record = make_record(
        post_url="https://linkedin.com/posts/2",
        author_linkedin_url="https://linkedin.com/in/janedoe",  # different recruiter
        primary_email="careers@example.com",  # different email
        company="ABC Technologies",
        job_role="Java Developer",
        job_location="Mumbai",
    )
    dup_of, reason = find_duplicate(new_record, db)
    assert dup_of == "https://linkedin.com/posts/1"
    assert reason == "COMPANY_ROLE_LOCATION"
    db.close()


def test_same_author_similar_text_duplicate_without_job_metadata(tmp_path):
    """
    Reproduces a real case: the same post, with no company/role/location
    extracted (so AUTHOR_SAME_JOB can't engage at all), appeared twice in
    one run under two different synthetic post_urls - with two different
    but related emails ("amresh@..." vs "dm.amresh@..."), presumably both
    mentioned in the one real post. author_linkedin_url + a shared text
    prefix is what should catch this.
    """
    db = Database(tmp_path / "test.db")
    shared_text = (
        "Hiring for a backend role, immediate joiner preferred, apply via "
        "email with your resume attached"
    )
    db.upsert(
        make_record(
            post_url="synthetic:https://linkedin.com/in/amreshsharma/|Hiring for a backend",
            post_text=shared_text,
            author_linkedin_url="https://linkedin.com/in/amreshsharma/",
            author_name="Amresh Sharma",
            company=None,
            job_role=None,
            job_location=None,
            primary_email="amresh@agileventures.net",
        )
    )

    new_record = make_record(
        post_url="synthetic:https://linkedin.com/in/amreshsharma/|Hiring for a backend role imm",
        post_text=shared_text,
        author_linkedin_url="https://linkedin.com/in/amreshsharma/",
        author_name="Amresh Sharma",
        company=None,
        job_role=None,
        job_location=None,
        primary_email="dm.amresh@agileventures.net",
    )
    dup_of, reason = find_duplicate(new_record, db)
    assert dup_of == "synthetic:https://linkedin.com/in/amreshsharma/|Hiring for a backend"
    assert reason == "AUTHOR_SAME_TEXT"
    db.close()


def test_same_author_different_text_not_flagged_as_duplicate(tmp_path):
    """A recruiter posting two genuinely different jobs must NOT be merged -
    only a shared text prefix (not just the same author) should match."""
    db = Database(tmp_path / "test.db")
    db.upsert(
        make_record(
            post_url="https://linkedin.com/posts/1",
            post_text="Hiring Java Developer for our Mumbai team, apply now",
            author_linkedin_url="https://linkedin.com/in/amreshsharma/",
            company=None,
            job_role=None,
            job_location=None,
            primary_email="amresh@agileventures.net",
        )
    )

    new_record = make_record(
        post_url="https://linkedin.com/posts/2",
        post_text="We're also looking for a QA Engineer, remote friendly role",
        author_linkedin_url="https://linkedin.com/in/amreshsharma/",
        company=None,
        job_role=None,
        job_location=None,
        primary_email="dm.amresh@agileventures.net",
    )
    dup_of, reason = find_duplicate(new_record, db)
    assert dup_of is None
    assert reason is None
    db.close()


def test_no_false_positive_on_different_job(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert(
        make_record(
            post_url="https://linkedin.com/posts/1",
            company="ABC Technologies",
            job_role="Java Developer",
            job_location="Mumbai",
            primary_email="jobs@example.com",
            author_linkedin_url="https://linkedin.com/in/johndoe",
        )
    )

    new_record = make_record(
        post_url="https://linkedin.com/posts/2",
        company="XYZ Corp",
        job_role="Backend Developer",
        job_location="Bangalore",
        primary_email="careers@xyz.com",
        author_linkedin_url="https://linkedin.com/in/janedoe",
    )
    dup_of, reason = find_duplicate(new_record, db)
    assert dup_of is None
    assert reason is None
    db.close()


def test_image_hash_duplicate_catches_reposted_flyer_different_everything(tmp_path):
    from PIL import Image

    from tests.factories import make_flyer_image

    # Same flyer graphic, but re-saved (simulating a repost), plus a
    # completely different author/company/role/location/email - none of the
    # first 4 dedup rules can catch this on their own.
    original = make_flyer_image(tmp_path / "orig.png", ["Hiring Java Developer", "Mumbai"])
    reposted = tmp_path / "reposted.jpg"
    Image.open(original).convert("RGB").resize((300, 200)).save(reposted, "JPEG", quality=80)

    from ocr.image_hash import compute_phash

    db = Database(tmp_path / "test.db")
    db.upsert(
        make_record(
            post_url="https://linkedin.com/posts/1",
            company="ABC Technologies",
            job_role="Java Developer",
            job_location="Mumbai",
            primary_email="jobs@example.com",
            author_linkedin_url="https://linkedin.com/in/johndoe",
        )
    )
    db.get_by_post_url("https://linkedin.com/posts/1")  # sanity: row exists
    # Manually attach an image hash to the stored record the way pipeline.py
    # would (make_record has no image_hashes param - patch it directly).
    stored = db.get_by_post_url("https://linkedin.com/posts/1")
    stored.extracted.image_hashes = [compute_phash(original)]
    db.upsert(stored)

    new_record = make_record(
        post_url="https://linkedin.com/posts/2",
        company="XYZ Corp",
        job_role="Backend Developer",
        job_location="Bangalore",
        primary_email="careers@xyz.com",
        author_linkedin_url="https://linkedin.com/in/janedoe",
    )
    new_record.extracted.image_hashes = [compute_phash(reposted)]

    dup_of, reason = find_duplicate(new_record, db)
    assert dup_of == "https://linkedin.com/posts/1"
    assert reason == "IMAGE_HASH"
    db.close()


def test_image_hash_not_matched_beyond_configured_distance(tmp_path):
    from ocr.image_hash import compute_phash
    from tests.factories import make_flyer_image

    flyer_a = make_flyer_image(tmp_path / "a.png", ["Hiring Java Developer", "Mumbai"])
    flyer_b = make_flyer_image(tmp_path / "b.png", ["Completely different birthday content"])

    db = Database(tmp_path / "test.db")
    db.upsert(make_record(post_url="https://linkedin.com/posts/1"))
    stored = db.get_by_post_url("https://linkedin.com/posts/1")
    stored.extracted.image_hashes = [compute_phash(flyer_a)]
    db.upsert(stored)

    new_record = make_record(
        post_url="https://linkedin.com/posts/2",
        company="Different Co",
        job_role="Different Role",
        job_location="Different City",
        primary_email="different@example.com",
        author_linkedin_url="https://linkedin.com/in/different",
    )
    new_record.extracted.image_hashes = [compute_phash(flyer_b)]

    # Strict threshold (0) - visually different images must not match.
    dup_of, reason = find_duplicate(new_record, db, image_hash_max_distance=0)
    assert dup_of is None
    assert reason is None
    db.close()


# --- v11: skipped records must not swallow later valid posts ----------------


def test_skipped_pune_post_does_not_make_mumbai_post_an_email_duplicate(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert(make_record(post_url="u1", job_location="Pune", status=RecordStatus.SKIPPED,
                          location_match=False))
    new = make_record(post_url="u2", job_location="Mumbai")
    assert find_duplicate(new, db) == (None, None)


def test_live_record_still_flags_email_duplicate(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert(make_record(post_url="u1", status=RecordStatus.REJECTED))
    assert find_duplicate(make_record(post_url="u2"), db) == ("u1", "EMAIL")


def test_exact_url_match_still_applies_to_skipped_records(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert(make_record(post_url="u1", status=RecordStatus.SKIPPED))
    assert find_duplicate(make_record(post_url="u1"), db) == ("u1", "POST_URL")
