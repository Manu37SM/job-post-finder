from core.models import WorkMode
from filtering.exclusions import check_exclusion
from filtering.location import location_decision

MUMBAI_ALIASES = ["Mumbai", "Bombay", "Mumbai Metropolitan Region", "MMR"]

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


def test_mumbai_any_work_mode_accepts():
    for mode in (WorkMode.ONSITE, WorkMode.HYBRID, WorkMode.REMOTE, WorkMode.UNKNOWN):
        match, reason = location_decision("Mumbai", mode, MUMBAI_ALIASES)
        assert match is True
        assert reason == "MUMBAI_MATCH"


def test_mumbai_alias_bombay_accepts():
    match, reason = location_decision("Bombay", WorkMode.ONSITE, MUMBAI_ALIASES)
    assert match is True


def test_mmr_alias_accepts():
    match, reason = location_decision("MMR", WorkMode.UNKNOWN, MUMBAI_ALIASES)
    assert match is True


def test_thane_is_not_a_mumbai_alias_by_default():
    match, reason = location_decision("Thane", WorkMode.ONSITE, MUMBAI_ALIASES)
    assert match is False


def test_non_mumbai_explicit_remote_accepts():
    match, reason = location_decision("Bangalore", WorkMode.REMOTE, MUMBAI_ALIASES)
    assert match is True
    assert reason == "EXPLICIT_REMOTE"


def test_non_mumbai_hybrid_rejects():
    match, reason = location_decision("Pune", WorkMode.HYBRID, MUMBAI_ALIASES)
    assert match is False
    assert reason.startswith("NON_MUMBAI_NON_REMOTE")


def test_non_mumbai_onsite_rejects():
    match, reason = location_decision("Bangalore", WorkMode.ONSITE, MUMBAI_ALIASES)
    assert match is False


def test_non_mumbai_unknown_mode_rejects():
    match, reason = location_decision("Chennai", WorkMode.UNKNOWN, MUMBAI_ALIASES)
    assert match is False


def test_unknown_location_rejects_even_with_remote_mode_elsewhere_implied():
    match, reason = location_decision(None, WorkMode.UNKNOWN, MUMBAI_ALIASES)
    assert match is False
    assert reason == "UNKNOWN_LOCATION"


def test_exclusion_matches_keyword():
    excluded, matched = check_exclusion("Join our Java Bootcamp today", EXCLUDE_KEYWORDS)
    assert excluded is True
    assert matched == "bootcamp"


def test_exclusion_no_match():
    excluded, matched = check_exclusion("Hiring Java Developer - Mumbai", EXCLUDE_KEYWORDS)
    assert excluded is False
    assert matched is None


def test_exclusion_does_not_reject_on_single_ordinary_word_not_in_list():
    # "developer" alone isn't an exclude keyword - only exact configured ones count.
    excluded, matched = check_exclusion("Hiring Java Developer", EXCLUDE_KEYWORDS)
    assert excluded is False
