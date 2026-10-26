import json

import pytest

from linkedin.fixture_source import discover_posts


def _write_fixture(path, posts):
    path.write_text(json.dumps(posts))


def test_discover_posts_basic(tmp_path):
    fixture = tmp_path / "posts.json"
    _write_fixture(
        fixture,
        [
            {
                "post_url": "https://linkedin.com/posts/1",
                "post_text": "Hiring Java Developer - Mumbai",
                "author_name": "John Doe",
            }
        ],
    )
    posts = discover_posts(fixture)
    assert len(posts) == 1
    assert posts[0].post_url == "https://linkedin.com/posts/1"
    assert posts[0].author_name == "John Doe"


def test_discover_posts_missing_optional_fields_default_sensibly(tmp_path):
    fixture = tmp_path / "posts.json"
    _write_fixture(fixture, [{"post_url": "https://linkedin.com/posts/1"}])
    posts = discover_posts(fixture)
    assert posts[0].post_text == ""
    assert posts[0].image_urls == []
    assert posts[0].author_name is None


def test_discover_posts_respects_max_posts(tmp_path):
    fixture = tmp_path / "posts.json"
    _write_fixture(
        fixture,
        [{"post_url": f"https://linkedin.com/posts/{i}"} for i in range(5)],
    )
    posts = discover_posts(fixture, max_posts=2)
    assert len(posts) == 2


def test_discover_posts_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        discover_posts(tmp_path / "does-not-exist.json")
