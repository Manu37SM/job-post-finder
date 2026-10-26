from core.models import Confidence, EmailSource, ExtractedPost, RawPost, SourceType, WorkMode
from filtering.relevance import compute_relevance


def _extracted(**overrides) -> ExtractedPost:
    raw = RawPost(post_url="https://linkedin.com/posts/1", post_text="text")
    defaults = dict(
        raw=raw,
        source_type=SourceType.TEXT,
        company=None,
        job_role=None,
        role_confidence=Confidence.NONE,
        job_location=None,
        location_confidence=Confidence.NONE,
        work_mode=WorkMode.UNKNOWN,
        all_emails=[],
        primary_email=None,
        email_source=EmailSource.NONE,
    )
    defaults.update(overrides)
    return ExtractedPost(**defaults)


def test_full_signal_stack_scores_five():
    ep = _extracted(
        company="ABC Technologies Pvt Ltd",
        job_role="Java Developer",
        role_confidence=Confidence.HIGH,
        job_location="Mumbai",
        work_mode=WorkMode.ONSITE,
        primary_email="jobs@example.com",
    )
    score, reasons = compute_relevance(ep, location_match=True, role_match=True, hiring_signal=True)
    assert score == 5
    assert "Java Developer detected" in reasons
    assert "Mumbai detected" in reasons
    assert "Hiring language detected" in reasons
    assert "Recruitment email detected" in reasons
    assert any(r.startswith("Company detected") for r in reasons)


def test_no_signals_scores_zero():
    ep = _extracted()
    score, reasons = compute_relevance(ep, location_match=False, role_match=False, hiring_signal=False)
    assert score == 0
    assert reasons == []


def test_remote_reason_instead_of_location_name():
    ep = _extracted(job_location="Bangalore", work_mode=WorkMode.REMOTE)
    score, reasons = compute_relevance(ep, location_match=True, role_match=False, hiring_signal=False)
    assert "Remote detected" in reasons
    assert "Bangalore detected" not in reasons


def test_medium_role_confidence_uses_partial_signal_reason():
    ep = _extracted(job_role=None, role_confidence=Confidence.MEDIUM)
    score, reasons = compute_relevance(ep, location_match=False, role_match=True, hiring_signal=False)
    assert "Partial Java role signal detected" in reasons


def test_role_match_false_contributes_nothing_even_with_role_set():
    # role_match is computed upstream (filtering/role.py) - this function
    # trusts that boolean rather than re-deriving it from role_confidence.
    ep = _extracted(job_role="Java Developer", role_confidence=Confidence.HIGH)
    score, reasons = compute_relevance(ep, location_match=False, role_match=False, hiring_signal=False)
    assert score == 0
    assert reasons == []
