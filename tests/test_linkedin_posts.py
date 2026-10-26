"""
Tests parse_post_element()'s WRAPPER behavior only (None-handling, exception
safety) - the actual extraction JS it runs via el.evaluate() is validated
separately against 36 real captured LinkedIn posts via Node+jsdom (see
linkedin/posts.py's module docstring for that process and its results).
These tests use FakePostElement.evaluate() to simulate what a real
Playwright element.evaluate() call would return, without needing a JS
runtime here.
"""

from linkedin.posts import parse_post_element
from tests.factories import FakePostElement


def test_returns_result_dict_when_evaluate_succeeds():
    el = FakePostElement(
        evaluate_result={
            "post_url": "https://www.linkedin.com/jobs/view/12345/",
            "post_text": "Hiring Java Developer - Mumbai",
            "image_urls": [],
            "author_name": "John Doe",
            "author_linkedin_url": "https://www.linkedin.com/in/johndoe/",
            "author_headline": "Recruiter at ABC",
            "post_date": None,
        }
    )
    result = parse_post_element(el)
    assert result["post_url"] == "https://www.linkedin.com/jobs/view/12345/"
    assert result["author_name"] == "John Doe"


def test_returns_synthetic_url_result_unchanged():
    """The JS itself builds the synthetic: fallback when no real permalink
    exists (see linkedin/posts.py) - parse_post_element must not alter or
    reject it, just pass it through like any other post_url."""
    el = FakePostElement(
        evaluate_result={
            "post_url": "synthetic:https://www.linkedin.com/in/johndoe/|Hiring Java Developer",
            "post_text": "Hiring Java Developer",
            "image_urls": [],
            "author_name": "John Doe",
            "author_linkedin_url": "https://www.linkedin.com/in/johndoe/",
            "author_headline": None,
            "post_date": None,
        }
    )
    result = parse_post_element(el)
    assert result["post_url"].startswith("synthetic:")


def test_none_result_from_evaluate_returns_none():
    el = FakePostElement(evaluate_result=None)
    assert parse_post_element(el) is None


def test_missing_post_url_key_returns_none():
    el = FakePostElement(evaluate_result={"post_text": "no url here"})
    assert parse_post_element(el) is None


def test_empty_post_url_returns_none():
    el = FakePostElement(evaluate_result={"post_url": "", "post_text": "x"})
    assert parse_post_element(el) is None


def test_evaluate_exception_returns_none_instead_of_raising():
    el = FakePostElement(raise_on_evaluate=True)
    assert parse_post_element(el) is None
