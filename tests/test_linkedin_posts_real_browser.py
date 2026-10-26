"""
Regression test for the extraction JS in linkedin/posts.py, using a REAL
Playwright browser (not fakes) against synthetic HTML built to match the
DOM shape validated against 36 real captured LinkedIn posts (see
linkedin/posts.py's module docstring for that validation).

Skips automatically if Chromium isn't installed (`playwright install
chromium`) - which this sandbox doesn't have, so this test could only be
confirmed to skip cleanly here, not to pass. It WILL run for real on any
machine set up for --live (i.e. yours), since that already requires the
same browser install - this is the one test in the suite that can catch a
real LinkedIn markup change (a different DOM shape, not just a different
class name) before you find out via a live run returning zero posts again.
"""

import pytest

from linkedin.posts import POST_CONTAINER_SELECTOR, parse_post_element

SYNTHETIC_POST_HTML = """
<html><body>
<div role="listitem">
  <div>
    <div>
      <a href="https://www.linkedin.com/in/janerecruiter/">
        <img src="https://media.licdn.com/avatar.jpg" width="20" height="20" />
        <span>Jane Recruiter</span>
      </a>
      <span>&bull; 2nd</span>
      <span>Talent Acquisition at ExampleCo</span>
      <span>3h</span>
    </div>
  </div>
  <p>Hiring: Java Developer - join our backend team building scalable
     services. Send your resume to jobs@example.com to apply.</p>
  <span>Mumbai (On-site)</span>
  <a href="https://www.linkedin.com/jobs/view/999999999/">View job</a>
  <img src="https://media.licdn.com/flyer.jpg" width="400" height="500" />
</div>
</body></html>
"""


@pytest.fixture(scope="module")
def browser_page():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            yield page
            browser.close()
    except Exception as e:
        pytest.skip(f"Chromium not available (run `playwright install chromium`): {e}")


def test_tracking_id_stripped_from_job_link_post_url(browser_page):
    """
    Regression test for a real bug found against a user's live dataset:
    30 of 53 distinct jobs appeared as 2-6 "separate" rows each, because
    LinkedIn appends a per-render ?trackingId=...&isJobSearch=... to
    /jobs/view/ links that changes every time the same job card renders.
    Two renders of the literal same job, differing only in that tracking
    query string, must produce the SAME post_url.
    """
    html_a = SYNTHETIC_POST_HTML.replace(
        "https://www.linkedin.com/jobs/view/999999999/",
        "https://www.linkedin.com/jobs/view/999999999/?trackingId=AAAA%3D%3D&isJobSearch=f",
    )
    html_b = SYNTHETIC_POST_HTML.replace(
        "https://www.linkedin.com/jobs/view/999999999/",
        "https://www.linkedin.com/jobs/view/999999999/?trackingId=BBBB%2BCC%3D%3D&isJobSearch",
    )

    browser_page.set_content(html_a)
    result_a = parse_post_element(browser_page.locator(POST_CONTAINER_SELECTOR).first)

    browser_page.set_content(html_b)
    result_b = parse_post_element(browser_page.locator(POST_CONTAINER_SELECTOR).first)

    assert result_a["post_url"] == result_b["post_url"] == "https://www.linkedin.com/jobs/view/999999999/"


def test_see_more_suffix_stripped_with_or_without_space(browser_page):
    """
    Regression test for a real bug found against a user's live dataset: the
    "see more" toggle text trailing a clamped post sometimes renders as
    "\u2026 more" (with a space) and sometimes "\u2026more" (no space) - the
    original strip pattern only matched the no-space form, leaving the
    spaced form ("... more") appended to extracted post_text.
    """
    for suffix in ("\u2026more", "\u2026 more", "\u2026MORE"):
        html = SYNTHETIC_POST_HTML.replace(
            "Send your resume to jobs@example.com to apply.",
            f"Send your resume to jobs@example.com to apply.{suffix}",
        )
        browser_page.set_content(html)
        el = browser_page.locator(POST_CONTAINER_SELECTOR).first
        result = parse_post_element(el)
        assert "more" not in result["post_text"].lower(), f"failed to strip suffix: {suffix!r}"
        # The fixture's job-card "Location: Mumbai (On-site)" line is
        # appended AFTER the "...more" strip step, so "to apply." is
        # followed by that, not the end of the string.
        assert "to apply.\nLocation: Mumbai (On-site)" in result["post_text"]


def test_real_extraction_against_synthetic_post(browser_page):
    browser_page.set_content(SYNTHETIC_POST_HTML)
    el = browser_page.locator(POST_CONTAINER_SELECTOR).first
    result = parse_post_element(el)

    assert result is not None
    assert result["author_name"] == "Jane Recruiter"
    assert result["author_headline"] == "Talent Acquisition at ExampleCo"
    assert result["author_linkedin_url"] == "https://www.linkedin.com/in/janerecruiter/"
    assert "Hiring: Java Developer" in result["post_text"]
    assert "jobs@example.com" in result["post_text"]
    # The structured "Mumbai (On-site)" line should have been folded in as a
    # labeled line for extraction/location_extractor.py to pick up.
    assert "Location: Mumbai (On-site)" in result["post_text"]
    # Real /jobs/view/ link present -> used as post_url, not the synthetic fallback.
    assert result["post_url"] == "https://www.linkedin.com/jobs/view/999999999/"
    # Tiny avatar excluded, larger flyer image included.
    assert result["image_urls"] == ["https://media.licdn.com/flyer.jpg"]


def test_br_line_break_after_email_does_not_mangle_it(browser_page):
    """
    Regression test for a real bug found on a user's first live run:
    .textContent (the original implementation) does not insert a separator
    across a <br>, so "...jobs@example.com<br>Please apply ASAP" extracted
    as "...jobs@example.comPlease apply ASAP" - email_extractor.py's regex
    then happily matched "gmail.commandatory"-style garbage as a TLD. Fixed
    by switching to .innerText (see linkedin/posts.py's docstring).
    """
    html = SYNTHETIC_POST_HTML.replace(
        "Send your resume to jobs@example.com to apply.",
        "Send your resume to jobs@example.com<br>Please apply ASAP, mandatory.",
    )
    browser_page.set_content(html)
    el = browser_page.locator(POST_CONTAINER_SELECTOR).first
    result = parse_post_element(el)

    assert result is not None
    assert "jobs@example.com" in result["post_text"]
    # The real symptom: without the fix, this would read
    # "jobs@example.comPlease apply ASAP, mandatory." - a line break, not
    # nothing, must separate the email from what follows.
    assert "jobs@example.comPlease" not in result["post_text"]


def test_real_extraction_falls_back_to_synthetic_url_without_a_job_link(browser_page):
    html = SYNTHETIC_POST_HTML.replace(
        '<a href="https://www.linkedin.com/jobs/view/999999999/">View job</a>', ""
    )
    browser_page.set_content(html)
    el = browser_page.locator(POST_CONTAINER_SELECTOR).first
    result = parse_post_element(el)

    assert result is not None
    assert result["post_url"].startswith("synthetic:")
    assert "janerecruiter" in result["post_url"]


MAILTO_POST_HTML = """
<div role="listitem">
  <a href="https://www.linkedin.com/in/jane/"><span>Jane Recruiter</span></a>
  <span>Hiring Java Developer in Mumbai. Mail your CV to our HR desk.</span>
  <a href="mailto:hr%2Bjava@acme.com?subject=Java">Click here to apply</a>
</div>
"""


def test_mailto_link_address_is_captured(browser_page):
    browser_page.set_content(MAILTO_POST_HTML)
    result = parse_post_element(browser_page.locator(POST_CONTAINER_SELECTOR).first)
    assert result is not None
    assert "Contact: hr+java@acme.com" in result["post_text"]
    # Identity must not depend on the appended contact line.
    assert result["post_url"].startswith("synthetic:https://www.linkedin.com/in/jane/|Hiring Java")
    assert "Contact" not in result["post_url"]


EXPAND_HTML = """
<div role="listitem">
  <a href="https://www.linkedin.com/in/sam/"><span>Sam Recruiter</span></a>
  <span id="body">Hiring Java Developer Mumbai <button id="m" onclick="
      document.getElementById('body').innerText='Hiring Java Developer Mumbai. Send CV to sam@acme.com';
      this.remove();">… more</button></span>
</div>
"""


def test_see_more_is_expanded_so_hidden_email_is_visible(browser_page):
    browser_page.set_content(EXPAND_HTML)
    result = parse_post_element(browser_page.locator(POST_CONTAINER_SELECTOR).first)
    assert result is not None
    assert "sam@acme.com" in result["post_text"]


def _post_with_age(age):
    return SYNTHETIC_POST_HTML.replace("<span>3h</span>", f"<span>{age}</span>")


@pytest.mark.parametrize("age", ["3mo", "1yr", "2 weeks", "5w", "1mo • Edited"])
def test_author_found_for_older_post_ages(browser_page, age):
    """Regression (v11): 'mo'/'yr' ages never matched, so author name came back null for every older post."""
    browser_page.set_content(_post_with_age(age))
    result = parse_post_element(browser_page.locator(POST_CONTAINER_SELECTOR).first)
    assert result["author_name"] == "Jane Recruiter"
    assert result["author_headline"] == "Talent Acquisition at ExampleCo"


def test_author_name_falls_back_to_link_text_without_any_timestamp(browser_page):
    browser_page.set_content(SYNTHETIC_POST_HTML.replace("<span>3h</span>", ""))
    result = parse_post_element(browser_page.locator(POST_CONTAINER_SELECTOR).first)
    assert result["author_name"] == "Jane Recruiter"
