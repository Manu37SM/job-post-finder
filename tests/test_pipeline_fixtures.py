"""
Replicates the 8 ACCEPT/REJECT fixtures from the project spec, wiring together
extraction + filtering exactly as the future pipeline module will. Image-OCR
cases (5, 6) are simulated by passing the "post-OCR" text directly, since the
OCR engine itself isn't built yet (that's the next stage) - this test only
proves the extraction/filtering wiring is correct once OCR hands it text.
"""

from extraction.email_extractor import extract_emails
from extraction.location_extractor import extract_location, extract_work_mode
from extraction.role_extractor import extract_role
from filtering.exclusions import check_exclusion
from filtering.location import location_decision
from filtering.role import role_matches

TARGET_ROLES = [
    "Java Developer",
    "Java Engineer",
    "Java Backend Developer",
    "Backend Developer",
    "Spring Boot Developer",
    "Software Engineer",
    "Full Stack Developer",
]

MUMBAI_ALIASES = ["Mumbai", "Bombay", "Mumbai Metropolitan Region", "MMR"]

REMOTE_TERMS = [
    "Remote",
    "Fully Remote",
    "Remote - India",
    "India Remote",
    "Work From Home",
    "WFH",
    "Remote anywhere in India",
]

EXCLUDE_KEYWORDS = [
    "course",
    "training",
    "bootcamp",
    "certification",
    "tutorial",
    "learn java",
    "job seeker",
    "looking for job",
    "resume service",
]


def run_pipeline(text: str) -> bool:
    """Minimal stand-in for the future pipeline.py: returns True iff the post
    would end up ACCEPTed (excluded posts and location rejects both -> False)."""
    excluded, _ = check_exclusion(text, EXCLUDE_KEYWORDS)
    if excluded:
        return False

    job_location, _ = extract_location(text)
    work_mode = extract_work_mode(text, REMOTE_TERMS)
    location_match, _ = location_decision(job_location, work_mode, MUMBAI_ALIASES)
    if not location_match:
        return False

    _, role_confidence = extract_role(text, TARGET_ROLES)
    return role_matches(role_confidence)


def test_case_1_text_mumbai_accepts():
    text = "Hiring Java Developer\nLocation: Mumbai\nSend CV to jobs@example.com"
    assert run_pipeline(text) is True


def test_case_2_text_pune_rejects():
    text = "Hiring Java Developer\nLocation: Pune\nSend CV to jobs@example.com"
    assert run_pipeline(text) is False


def test_case_3_text_bangalore_remote_accepts():
    text = "Hiring Java Developer\nLocation: Bangalore\nRemote - India"
    assert run_pipeline(text) is True


def test_case_4_text_bangalore_hybrid_rejects():
    text = "Hiring Java Developer\nLocation: Bangalore\nHybrid"
    assert run_pipeline(text) is False


def test_case_5_ocr_mumbai_accepts():
    # Simulated post-OCR text (real image OCR arrives in the next stage).
    text = "URGENT HIRING\nJava Developer\nMumbai\njobs@example.com"
    assert run_pipeline(text) is True


def test_case_6_ocr_pune_rejects():
    text = "Java Developer\nPune\njobs@example.com"
    assert run_pipeline(text) is False


def test_case_7_no_location_rejects():
    text = "Hiring Java Developer\njobs@example.com"
    assert run_pipeline(text) is False


def test_case_8_course_advertisement_rejects():
    text = "Learn Java Developer skills\nJoin our Java Bootcamp"
    assert run_pipeline(text) is False


# Extra edge cases from the spec's HQ-vs-job-location and alias-scoping sections.


def test_extra_hq_bangalore_job_mumbai_accepts():
    text = "Company headquartered in Bangalore. Hiring Java Developer — Mumbai"
    assert run_pipeline(text) is True


def test_extra_hq_mumbai_job_bangalore_onsite_rejects():
    text = "Company headquartered in Mumbai. Hiring Java Developer — Bangalore"
    assert run_pipeline(text) is False


def test_extra_hq_mumbai_job_remote_india_accepts():
    text = "Company headquartered in Mumbai. Hiring Java Developer — Remote India"
    assert run_pipeline(text) is True


def test_extra_thane_rejects_in_v1():
    text = "Hiring Java Developer — Thane"
    assert run_pipeline(text) is False


def test_extra_email_extraction_wired_correctly():
    text = "Hiring Java Developer - Mumbai. Send CV to jobs@example.com"
    all_emails, primary, source = extract_emails(text, "")
    assert primary == "jobs@example.com"
    assert all_emails == ["jobs@example.com"]
