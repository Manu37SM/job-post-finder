from core.models import Confidence
from extraction.role_extractor import extract_role

TARGET_ROLES = [
    "Java Developer",
    "Java Engineer",
    "Java Backend Developer",
    "Backend Developer",
    "Spring Boot Developer",
    "Software Engineer",
    "Full Stack Developer",
]


def test_exact_role_match():
    role, conf = extract_role("Hiring Java Developer in Mumbai", TARGET_ROLES)
    assert role == "Java Developer"
    assert conf == Confidence.HIGH


def test_longest_phrase_wins_over_shorter_overlapping_alias():
    role, conf = extract_role(
        "We are hiring a Java Backend Developer for our Mumbai office", TARGET_ROLES
    )
    assert role == "Java Backend Developer"
    assert conf == Confidence.HIGH


def test_no_role_configured_match_but_partial_java_signal():
    role, conf = extract_role("Looking for a Java guy, developer role", TARGET_ROLES)
    assert role is None
    assert conf == Confidence.MEDIUM


def test_no_signal_at_all():
    role, conf = extract_role("We sell furniture in Mumbai", TARGET_ROLES)
    assert role is None
    assert conf == Confidence.NONE


def test_does_not_treat_every_java_mention_as_a_job():
    # "Java" appears (as in a coffee-shop post) with no role word nearby.
    role, conf = extract_role("Best Java coffee beans in Mumbai", TARGET_ROLES)
    assert role is None
    assert conf == Confidence.NONE


def test_empty_text():
    role, conf = extract_role("", TARGET_ROLES)
    assert role is None
    assert conf == Confidence.NONE
