from pathlib import Path

import pytest

from linkedin.posts import POST_CONTAINER_SELECTOR
from linkedin.search import build_search_url, search_posts
from linkedin.session import SessionExpiredError
from tests.factories import make_fake_post_element


class _FakeMouse:
    def wheel(self, dx, dy):
        pass


class FakePage:
    """Simulates one FakePostElement 'batch' being returned per scroll -
    batches is a list of lists; running out of batches yields empty results
    (as if the feed stopped loading more)."""

    def __init__(self, batches, start_url="https://www.linkedin.com/"):
        self.url = start_url
        self._batches = iter(batches)
        self.mouse = _FakeMouse()
        self.goto_calls = []

    def goto(self, url, **kwargs):
        self.goto_calls.append(url)

    def wait_for_selector(self, selector, timeout=None):
        pass  # no-op by default; see FakePageThatNeverLoads below for the timeout case

    def locator(self, selector):
        assert selector == POST_CONTAINER_SELECTOR
        elements = next(self._batches, [])
        return _FakeLocatorList(elements)


class _FakeLocatorList:
    def __init__(self, elements):
        self._elements = elements

    def all(self):
        return self._elements


def test_build_search_url_encodes_spaces():
    url = build_search_url("Java Developer")
    assert "Java%20Developer" in url
    assert url.startswith("https://www.linkedin.com/search/results/content/?keywords=")


def test_search_posts_dedupes_across_scroll_batches(monkeypatch):
    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "MAX_SCROLLS", 3)
    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    post1 = make_fake_post_element("https://linkedin.com/posts/1")
    post2 = make_fake_post_element("https://linkedin.com/posts/2")
    post3 = make_fake_post_element("https://linkedin.com/posts/3")

    # Batch 1: posts 1, 2. Batch 2: post 2 re-rendered + post 3 (typical
    # LinkedIn infinite-scroll behavior - already-seen elements reappear).
    page = FakePage(batches=[[post1, post2], [post2, post3]])

    results = search_posts(page, "Java Developer", max_posts=10)

    urls = [r["post_url"] for r in results]
    assert urls == [
        "https://linkedin.com/posts/1",
        "https://linkedin.com/posts/2",
        "https://linkedin.com/posts/3",
    ]


def test_search_posts_stops_at_max_posts(monkeypatch):
    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "MAX_SCROLLS", 3)
    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    post1 = make_fake_post_element("https://linkedin.com/posts/1")
    post2 = make_fake_post_element("https://linkedin.com/posts/2")
    page = FakePage(batches=[[post1, post2]])

    results = search_posts(page, "Java Developer", max_posts=1)
    assert len(results) == 1


def test_search_posts_raises_on_expired_session(monkeypatch):
    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "MAX_SCROLLS", 1)
    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    page = FakePage(batches=[], start_url="https://www.linkedin.com/login")
    with pytest.raises(SessionExpiredError):
        search_posts(page, "Java Developer", max_posts=10)


def test_wait_for_selector_timeout_does_not_raise_falls_through_to_empty_result(monkeypatch):
    """A stale/wrong selector (the most likely real-world cause of zero
    results) must not crash the run - it should fall through to the normal
    scroll loop, find nothing, and let the debug snapshot explain why."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "MAX_SCROLLS", 1)
    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    class FakePageTimesOut(FakePage):
        def wait_for_selector(self, selector, timeout=None):
            raise PlaywrightTimeoutError("Timeout waiting for selector")

    page = FakePageTimesOut(batches=[])
    results = search_posts(page, "Java Developer", max_posts=10, debug_dir=None)
    assert results == []


def test_zero_results_saves_debug_snapshot(monkeypatch, tmp_path):
    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "MAX_SCROLLS", 1)
    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    class FakePageWithScreenshot(FakePage):
        def screenshot(self, path, full_page=True):
            Path(path).write_bytes(b"fake-png-bytes")

        def content(self):
            return "<html><body>no posts here</body></html>"

    page = FakePageWithScreenshot(batches=[])
    debug_dir = tmp_path / "debug"
    results = search_posts(page, "Java Developer", max_posts=10, debug_dir=debug_dir)

    assert results == []
    assert (debug_dir / "Java_Developer.png").exists()
    assert (debug_dir / "Java_Developer.html").read_text() == "<html><body>no posts here</body></html>"


def test_debug_snapshot_skipped_when_debug_dir_is_none(monkeypatch, tmp_path):
    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "MAX_SCROLLS", 1)
    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    page = FakePage(batches=[])
    # Must not raise even though FakePage has no screenshot()/content() -
    # debug_dir=None means _save_debug_snapshot is never called.
    results = search_posts(page, "Java Developer", max_posts=10, debug_dir=None)
    assert results == []


def test_debug_snapshot_failure_does_not_raise(monkeypatch, tmp_path, capsys):
    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "MAX_SCROLLS", 1)
    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    class FakePageScreenshotFails(FakePage):
        def screenshot(self, path, full_page=True):
            raise RuntimeError("browser crashed")

        def content(self):
            return "<html></html>"

    page = FakePageScreenshotFails(batches=[])
    results = search_posts(page, "Java Developer", max_posts=10, debug_dir=tmp_path / "debug")
    assert results == []  # the real result - debug capture failing must not mask this
    assert "Could not save debug snapshot" in capsys.readouterr().out


def test_debug_snapshot_not_triggered_when_posts_found(monkeypatch, tmp_path):
    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "MAX_SCROLLS", 1)
    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    post1 = make_fake_post_element("https://linkedin.com/posts/1")
    page = FakePage(batches=[[post1]])
    debug_dir = tmp_path / "debug"
    results = search_posts(page, "Java Developer", max_posts=10, debug_dir=debug_dir)

    assert len(results) == 1
    assert not debug_dir.exists()


# ---- configurable scroll depth + early stop (config.json max_scrolls etc.) ----


class _CountingPage(FakePage):
    """FakePage that also records how many scroll passes actually happened
    (each pass calls locator(...).all() once)."""

    def __init__(self, batches, **kwargs):
        super().__init__(batches, **kwargs)
        self.locator_calls = 0

    def locator(self, selector):
        self.locator_calls += 1
        return super().locator(selector)


def test_explicit_max_scrolls_overrides_module_default(monkeypatch):
    import linkedin.search as search_module

    # Module default is tiny; the explicit argument (what app.py passes from
    # config.json) must win over it.
    monkeypatch.setattr(search_module, "MAX_SCROLLS", 1)
    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    batches = [[make_fake_post_element(f"https://linkedin.com/posts/{i}")] for i in range(5)]
    page = _CountingPage(batches=batches)

    results = search_posts(page, "Java Developer", max_posts=100, max_scrolls=5, scroll_pause_seconds=0)

    assert len(results) == 5
    assert page.locator_calls == 5


def test_none_max_scrolls_still_uses_monkeypatched_module_constant(monkeypatch):
    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "MAX_SCROLLS", 2)
    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    batches = [[make_fake_post_element(f"https://linkedin.com/posts/{i}")] for i in range(5)]
    page = _CountingPage(batches=batches)

    results = search_posts(page, "Java Developer", max_posts=100)  # no explicit max_scrolls
    assert len(results) == 2
    assert page.locator_calls == 2


def test_stops_early_when_feed_stops_yielding_new_posts(monkeypatch):
    """A generous max_scrolls must not cost time once the feed is exhausted:
    after STALE_SCROLL_LIMIT consecutive passes with nothing new, stop."""
    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    post1 = make_fake_post_element("https://linkedin.com/posts/1")
    # One real batch, then the feed runs dry (FakePage returns [] forever).
    page = _CountingPage(batches=[[post1]])

    results = search_posts(page, "Java Developer", max_posts=100, max_scrolls=50, scroll_pause_seconds=0)

    assert len(results) == 1
    # 1 productive pass + STALE_SCROLL_LIMIT empty passes, nowhere near 50.
    assert page.locator_calls == 1 + search_module.STALE_SCROLL_LIMIT


def test_stale_counter_resets_when_new_posts_arrive_again(monkeypatch):
    """A temporary stall (slow lazy-load) followed by more posts must NOT
    trigger the early stop - only *consecutive* empty passes count."""
    import linkedin.search as search_module

    monkeypatch.setattr(search_module, "SCROLL_PAUSE_SECONDS", 0)

    limit = search_module.STALE_SCROLL_LIMIT
    stall = [[] for _ in range(limit - 1)]  # one short of triggering the stop
    batches = (
        [[make_fake_post_element("https://linkedin.com/posts/1")]]
        + stall
        + [[make_fake_post_element("https://linkedin.com/posts/2")]]
    )
    page = _CountingPage(batches=batches)

    results = search_posts(page, "Java Developer", max_posts=100, max_scrolls=50, scroll_pause_seconds=0)

    assert [r["post_url"] for r in results] == [
        "https://linkedin.com/posts/1",
        "https://linkedin.com/posts/2",
    ]


def test_one_failing_search_term_does_not_lose_the_others(monkeypatch, tmp_path):
    """Regression (v11): a goto timeout on one term used to abort the whole run."""
    import contextlib

    import linkedin.search as search

    class _Browser:
        def close(self):
            pass

    class _Context:
        def new_page(self):
            return object()

    @contextlib.contextmanager
    def fake_sync_playwright():
        yield object()

    monkeypatch.setattr("playwright.sync_api.sync_playwright", fake_sync_playwright)
    monkeypatch.setattr(search, "new_context", lambda p, s, headless=True: (_Browser(), _Context()))
    monkeypatch.setattr(search, "download_images", lambda page, urls, dest: {})

    def fake_search(page, term, remaining, **kw):
        if term == "bad":
            raise TimeoutError("Page.goto: Timeout 30000ms exceeded")
        return [{"post_url": f"https://x/{term}", "post_text": "t", "image_urls": [],
                 "author_name": "a", "author_linkedin_url": None,
                 "author_headline": None, "post_date": None}]

    monkeypatch.setattr(search, "search_posts", fake_search)
    posts = search.discover_posts("s.json", ["good1", "bad", "good2"], 10, image_dest_dir=tmp_path)
    assert [p.post_url for p in posts] == ["https://x/good1", "https://x/good2"]


def test_session_expiry_still_aborts_the_run(monkeypatch, tmp_path):
    import contextlib

    import pytest

    import linkedin.search as search
    from linkedin.session import SessionExpiredError

    class _B:
        def close(self):
            pass

    class _C:
        def new_page(self):
            return object()

    @contextlib.contextmanager
    def fake_pw():
        yield object()

    monkeypatch.setattr("playwright.sync_api.sync_playwright", fake_pw)
    monkeypatch.setattr(search, "new_context", lambda p, s, headless=True: (_B(), _C()))

    def boom(*a, **k):
        raise SessionExpiredError("expired")

    monkeypatch.setattr(search, "search_posts", boom)
    with pytest.raises(SessionExpiredError):
        search.discover_posts("s.json", ["a"], 5, image_dest_dir=tmp_path)
