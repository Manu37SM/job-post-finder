from core.models import Confidence, WorkMode
from extraction.location_extractor import extract_location, extract_work_mode

REMOTE_TERMS = [
    "Remote",
    "Fully Remote",
    "Remote - India",
    "India Remote",
    "Work From Home",
    "WFH",
    "Remote anywhere in India",
]


def test_labeled_location_line_wins():
    loc, conf = extract_location("Hiring Java Developer\nLocation: Mumbai")
    assert loc == "Mumbai"
    assert conf == Confidence.HIGH


def test_labeled_location_with_state():
    loc, conf = extract_location("Location: Mumbai, Maharashtra")
    assert loc == "Mumbai, Maharashtra"
    assert conf == Confidence.HIGH


def test_unlabeled_city_mention():
    loc, conf = extract_location("Hiring Java Developer in Pune for our team")
    assert loc == "Pune"
    assert conf == Confidence.MEDIUM


def test_no_location_found():
    loc, conf = extract_location("Hiring Java Developer, send CV to jobs@example.com")
    assert loc is None
    assert conf == Confidence.NONE


def test_hq_context_excluded_job_location_still_found():
    text = "Company headquartered in Bangalore. Hiring Java Developer - Mumbai"
    loc, conf = extract_location(text)
    assert loc == "Mumbai"


def test_hq_context_only_no_job_location_elsewhere():
    text = "Company headquartered in Mumbai. Great place to work."
    loc, conf = extract_location(text)
    assert loc is None
    assert conf == Confidence.NONE


def test_hq_in_mumbai_job_in_bangalore_prefers_job_location():
    text = "Company headquartered in Mumbai. Hiring Java Developer - Bangalore"
    loc, conf = extract_location(text)
    assert loc == "Bangalore"


def test_thane_is_a_known_city_but_not_a_mumbai_alias():
    # extractor finds it as *a* location; whether it counts as "Mumbai" is a
    # filtering-layer/config decision, not this function's job.
    loc, conf = extract_location("Hiring Java Developer - Thane")
    assert loc == "Thane"


def test_work_mode_explicit_remote():
    assert extract_work_mode("Java Developer - Remote", REMOTE_TERMS) == WorkMode.REMOTE


def test_work_mode_wfh_alias():
    assert extract_work_mode("Java Developer - WFH", REMOTE_TERMS) == WorkMode.REMOTE


def test_work_mode_hybrid():
    assert extract_work_mode("Java Developer - Hybrid", REMOTE_TERMS) == WorkMode.HYBRID


def test_work_mode_onsite_wfo():
    assert extract_work_mode("Java Developer - WFO", REMOTE_TERMS) == WorkMode.ONSITE


def test_work_mode_unknown():
    assert extract_work_mode("Java Developer", REMOTE_TERMS) == WorkMode.UNKNOWN


def test_work_mode_empty_text():
    assert extract_work_mode("", REMOTE_TERMS) == WorkMode.UNKNOWN
