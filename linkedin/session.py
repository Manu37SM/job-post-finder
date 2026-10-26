"""
LinkedIn session handling - mirrors job-bot's save-session.js / linkedin.js
pattern exactly (confirmed from the uploaded job-bot source): a one-time
manual login saves Playwright's storageState to a JSON file; every run
loads that file into a fresh browser context. No credentials are ever
stored anywhere.

This is the ONLY module that touches session/auth state. search.py and
posts.py should never assume a session is valid on their own - always route
through ensure_logged_in() first, same as job-bot's linkedin.js does after
loading storageState.

VALIDATED as of this update: save_session() + new_context() +
ensure_logged_in() have now been confirmed working end-to-end in a real
--live run - login, storageState save/reload, and the /login-/authwall
check all behaved as designed.
"""

from pathlib import Path


class SessionExpiredError(Exception):
    """Raised when the loaded session lands on a login/authwall/checkpoint
    redirect. Rerun save_session() to refresh session-linkedin.json."""


def save_session(
    session_path: str | Path, login_url: str = "https://www.linkedin.com/login"
) -> None:
    """
    One-time manual login, mirroring job-bot's save-session.js: opens a
    real (non-headless) browser, waits for you to log in by hand (including
    any 2FA/checkpoint), then saves cookies to session_path. Run this once,
    standalone, whenever the session expires:

        python -c "from linkedin.session import save_session; save_session('session-linkedin.json')"
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url)
        input("Log in in the opened browser window, then press Enter here to save the session...")
        context.storage_state(path=str(session_path))
        browser.close()


def new_context(playwright, session_path: str | Path, headless: bool = True):
    """
    Loads a saved session into a fresh browser context - job-bot's
    `browser.newContext({ storageState: sessionFile })`, ported to Python.
    Returns (browser, context); caller is responsible for browser.close().
    """
    session_path = Path(session_path)
    if not session_path.exists():
        raise FileNotFoundError(
            f"{session_path} not found. Run save_session() first to create it."
        )
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(storage_state=str(session_path))
    return browser, context


def ensure_logged_in(page) -> None:
    """
    Raises SessionExpiredError if the current page landed on a login/
    authwall/checkpoint redirect - the same check job-bot's linkedin.js
    does after loading storageState, ported here so every browser-layer
    entry point can call it before scraping.
    """
    url = page.url
    if "/login" in url or "/authwall" in url or "/checkpoint/" in url:
        raise SessionExpiredError(
            f"LinkedIn session appears expired (landed on {url}). "
            "Run save_session() again to refresh session-linkedin.json."
        )
