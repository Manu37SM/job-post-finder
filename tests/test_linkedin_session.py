import pytest

from linkedin.session import SessionExpiredError, ensure_logged_in, new_context


class FakePage:
    def __init__(self, url):
        self.url = url


def test_ensure_logged_in_raises_on_login_redirect():
    with pytest.raises(SessionExpiredError):
        ensure_logged_in(FakePage("https://www.linkedin.com/login"))


def test_ensure_logged_in_raises_on_authwall():
    with pytest.raises(SessionExpiredError):
        ensure_logged_in(FakePage("https://www.linkedin.com/authwall?x=1"))


def test_ensure_logged_in_raises_on_checkpoint():
    with pytest.raises(SessionExpiredError):
        ensure_logged_in(FakePage("https://www.linkedin.com/checkpoint/challenge"))


def test_ensure_logged_in_passes_on_normal_page():
    # Should not raise.
    ensure_logged_in(FakePage("https://www.linkedin.com/search/results/content/?keywords=java"))


def test_new_context_missing_session_file_raises_before_touching_playwright(tmp_path):
    missing = tmp_path / "session-linkedin.json"
    # Passing None as the "playwright" object - the function must raise
    # FileNotFoundError before ever touching it, proving it checks the file
    # first rather than launching a browser only to fail later.
    with pytest.raises(FileNotFoundError):
        new_context(None, missing)
