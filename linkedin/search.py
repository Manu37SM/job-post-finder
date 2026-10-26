"""
Browser interaction layer for LinkedIn's post search: navigation,
pagination/scrolling, and orchestrating session + posts.py + images.py into
the same `discover_posts(arg, search_terms, max_posts) -> list[RawPost]`
shape linkedin/fixture_source.py already provides - this is what makes
swapping the stub source for this real one in app.py a one-line change.

VALIDATED AGAINST A REAL LIVE SESSION as of this update: a real --live run
discovered, extracted, OCR'd, and filtered 58 posts end-to-end (54 then 51
processed across two runs after fixing OCR's Windows PATH issue - see
ocr/tesseract.py). The navigate -> ensure_logged_in -> wait -> collect ->
scroll loop, pagination/dedup across search terms, and posts.py's
structural extraction have all now run against real LinkedIn, not just
fakes. What's still unverified: the exact scroll distance/pause tuning
(MAX_SCROLLS/SCROLL_PAUSE_SECONDS) was never measured against how many
results LinkedIn actually serves per scroll, so pages near the max_posts
boundary might be under- or over-scrolling - tune these two constants if
you notice you're consistently getting fewer posts than expected.

IMAGE HANDLING NOTE: like linkedin/fixture_source.py, this module returns
RawPost.image_urls containing LOCAL FILE PATHS (post-download), not the
original remote URLs - this keeps pipeline.py and app.py completely
unchanged (they already expect to treat image_urls entries as local paths
directly for the stub source). The tradeoff: the original CDN URL isn't
preserved on the RawPost itself. If you later want the real URL kept (e.g.
for the ocr-failures.csv log to show a clickable link instead of a temp
path), that means changing RawPost's shape and touching pipeline.py/app.py
- flagging this now rather than silently deciding it for you.
"""

import time
from pathlib import Path
from urllib.parse import quote

from core.models import RawPost
from linkedin.images import download_images
from linkedin.posts import POST_CONTAINER_SELECTOR, parse_post_element
from linkedin.session import SessionExpiredError, ensure_logged_in, new_context

SEARCH_URL_TEMPLATE = "https://www.linkedin.com/search/results/content/?keywords={keywords}"

# LinkedIn lazy-loads results as you scroll; too few scrolls and you miss
# posts, too many and it looks like automated traffic. Tune against a real
# session - these are conservative starting values, not measured ones.
MAX_SCROLLS = 15
SCROLL_PAUSE_SECONDS = 1.5

# Stop scrolling early once this many consecutive scroll passes add zero
# new posts - LinkedIn's feed has run out (or stalled), and every further
# pass would just burn SCROLL_PAUSE_SECONDS and add automated-looking
# traffic for nothing. This is what makes a generous max_scrolls ceiling
# in config.json cheap: you only pay for scrolls that actually find posts.
STALE_SCROLL_LIMIT = 4

# How long to wait for at least one post to render after navigating, before
# giving up and treating the search as genuinely empty. LinkedIn's feed is a
# heavy SPA - it renders content via XHR well after the initial page load,
# so querying immediately after goto() can find zero elements even with
# correct selectors. This was the first thing to check when a real run
# reported "Posts discovered: 0" with no error - see search_posts' docstring.
INITIAL_LOAD_TIMEOUT_MS = 10_000
GOTO_TIMEOUT_MS = 60_000


def build_search_url(term: str) -> str:
    return SEARCH_URL_TEMPLATE.format(keywords=quote(term))


def search_posts(
    page,
    term: str,
    max_posts: int,
    debug_dir: str | Path | None = "data/debug",
    max_scrolls: int | None = None,
    scroll_pause_seconds: float | None = None,
) -> list[dict]:
    """
    Navigates to the post-search results for `term`, scrolls to load more,
    and returns raw post dicts (see posts.parse_post_element for the
    shape). Stops once max_posts is reached, max_scrolls is exhausted, or
    STALE_SCROLL_LIMIT consecutive scrolls find nothing new.

    max_scrolls / scroll_pause_seconds default (None) to the module-level
    MAX_SCROLLS / SCROLL_PAUSE_SECONDS, looked up at call time rather than
    bound as default arguments - so tests that monkeypatch those module
    constants keep working, while app.py passes config.json's values
    explicitly.

    If zero posts are found for this term and debug_dir is not None, saves a
    screenshot and the full page HTML there - this is the fastest way to
    tell "selectors are wrong" (page has visible posts in the screenshot,
    zero found in the HTML matching POST_CONTAINER_SELECTOR) apart from
    "nothing loaded" (screenshot shows a blank/loading/blocked page) apart
    from "genuinely no results for this term" (screenshot shows LinkedIn's
    own empty-results message).
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    if max_scrolls is None:
        max_scrolls = MAX_SCROLLS
    if scroll_pause_seconds is None:
        scroll_pause_seconds = SCROLL_PAUSE_SECONDS

    # domcontentloaded, not the default "load": LinkedIn's SPA keeps
    # fetching in the background so "load" can time out even when the page
    # is perfectly usable (a real run hit exactly this goto timeout).
    page.goto(build_search_url(term), wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    ensure_logged_in(page)

    try:
        page.wait_for_selector(POST_CONTAINER_SELECTOR, timeout=INITIAL_LOAD_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        # Not fatal on its own - could mean the selector is stale (most
        # likely), the page is still loading, or there really are no
        # results. Fall through to the scroll loop (which will also find
        # nothing) rather than raising, so app.py's per-post error handling
        # doesn't need to change; the debug dump below is what actually
        # tells you which of the three it was.
        pass

    results: list[dict] = []
    seen_urls: set[str] = set()

    stale_scrolls = 0
    for _ in range(max_scrolls):
        if len(results) >= max_posts:
            break

        count_before = len(results)
        for el in page.locator(POST_CONTAINER_SELECTOR).all():
            if len(results) >= max_posts:
                break
            post = parse_post_element(el)
            if post is None or post["post_url"] in seen_urls:
                continue
            seen_urls.add(post["post_url"])
            results.append(post)

        if len(results) == count_before:
            stale_scrolls += 1
            if stale_scrolls >= STALE_SCROLL_LIMIT:
                break
        else:
            stale_scrolls = 0

        page.mouse.wheel(0, 3000)
        time.sleep(scroll_pause_seconds)

    if not results and debug_dir is not None:
        _save_debug_snapshot(page, term, debug_dir)

    return results[:max_posts]


def _save_debug_snapshot(page, term: str, debug_dir: str | Path) -> None:
    """Best-effort - a debug dump failing must never mask the real problem
    (zero results), so this never raises."""
    try:
        debug_dir = Path(debug_dir)
        debug_dir.mkdir(parents=True, exist_ok=True)
        safe_term = "".join(c if c.isalnum() else "_" for c in term)[:40]
        screenshot_path = debug_dir / f"{safe_term}.png"
        html_path = debug_dir / f"{safe_term}.html"
        page.screenshot(path=str(screenshot_path), full_page=True)
        html_path.write_text(page.content(), encoding="utf-8")
        print(
            f"[debug] Zero posts found for '{term}'. Saved {screenshot_path} and "
            f"{html_path} - open the screenshot to see what actually rendered, "
            f"and check that [role='listitem'] still matches LinkedIn's current "
            f"post-search markup (see linkedin/posts.py's module docstring for "
            f"why that selector, not a class name, is used)."
        )
    except Exception as e:  # noqa: BLE001 - debug capture is best-effort only
        print(f"[debug] Could not save debug snapshot for '{term}': {e}")


def discover_posts(
    session_path: str | Path,
    search_terms: list[str],
    max_posts: int,
    headless: bool = True,
    image_dest_dir: str | Path = "data/downloaded_images",
    max_scrolls: int | None = None,
    scroll_pause_seconds: float | None = None,
) -> list[RawPost]:
    """
    Top-level entry point - same call shape as
    linkedin.fixture_source.discover_posts(arg, search_terms, max_posts), so
    app.py's `discover_fn=linkedin.search.discover_posts,
    discover_arg=session_path` is a drop-in swap for the stub source.

    Runs every configured search term in one browser session, deduplicates
    by post_url across terms (the same job posted under two search terms
    would otherwise appear twice before pipeline.py's own dedup even runs),
    downloads images for each post, and stops once max_posts total posts
    have been collected across all terms.
    """
    from playwright.sync_api import sync_playwright

    all_posts: dict[str, dict] = {}  # post_url -> raw dict, dedup across search terms

    with sync_playwright() as p:
        browser, context = new_context(p, session_path, headless=headless)
        try:
            page = context.new_page()
            for term in search_terms:
                if len(all_posts) >= max_posts:
                    break
                remaining = max_posts - len(all_posts)
                try:
                    found = search_posts(
                        page,
                        term,
                        remaining,
                        max_scrolls=max_scrolls,
                        scroll_pause_seconds=scroll_pause_seconds,
                    )
                except SessionExpiredError:
                    raise  # a dead session fails every term - tell the user now
                except Exception as e:  # noqa: BLE001 - one bad term must not lose the rest
                    print(f"[search] '{term}' failed ({type(e).__name__}: {e}); continuing with the next term.")
                    continue
                for post in found:
                    all_posts.setdefault(post["post_url"], post)

            raw_posts = []
            for post in list(all_posts.values())[:max_posts]:
                local_images = download_images(page, post["image_urls"], image_dest_dir)
                raw_posts.append(
                    RawPost(
                        post_url=post["post_url"],
                        post_text=post["post_text"],
                        image_urls=list(local_images.values()),
                        author_name=post["author_name"],
                        author_linkedin_url=post["author_linkedin_url"],
                        author_headline=post["author_headline"],
                        post_date=post["post_date"],
                    )
                )
            return raw_posts
        finally:
            browser.close()
