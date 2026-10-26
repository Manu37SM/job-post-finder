"""
Stub post source so the full pipeline can run end-to-end without a real
LinkedIn session. Same public shape a future linkedin/search.py (Playwright)
will provide - discover_posts(search_terms, max_posts) -> list[RawPost] -
so app.py doesn't change when that lands; only which source it imports.

Fixture file format: a JSON list of objects with RawPost's fields. There's
no download step to simulate here, so `image_urls` entries are treated as
local file paths directly (a real scraper would download images and pass a
separate image_url -> local_path mapping to pipeline.process_post).
"""

import json
from pathlib import Path

from core.models import RawPost


def discover_posts(
    fixture_path: str | Path,
    search_terms: list[str] | None = None,
    max_posts: int | None = None,
    max_scrolls: int | None = None,
    scroll_pause_seconds: float | None = None,
) -> list[RawPost]:
    """
    search_terms, max_scrolls and scroll_pause_seconds are accepted for
    interface-compatibility with linkedin.search.discover_posts (app.py
    calls both sources identically) but ignored here - the fixture file already IS the result
    set. max_posts truncates it, same as the real source's config field.
    """
    path = Path(fixture_path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Create a fixture file (see data/sample_posts.json) "
            "or point --fixture at one."
        )
    raw_list = json.loads(path.read_text())
    posts = [
        RawPost(
            post_url=item["post_url"],
            post_text=item.get("post_text", ""),
            image_urls=item.get("image_urls", []),
            author_name=item.get("author_name"),
            author_linkedin_url=item.get("author_linkedin_url"),
            author_headline=item.get("author_headline"),
            post_date=item.get("post_date"),
        )
        for item in raw_list
    ]
    if max_posts is not None:
        posts = posts[:max_posts]
    return posts
