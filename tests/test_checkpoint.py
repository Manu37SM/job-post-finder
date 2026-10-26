from storage.checkpoint import read_checkpoint, write_checkpoint


def test_write_and_read_roundtrip(tmp_path):
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, posts_seen=3, last_post_url="https://linkedin.com/posts/3")

    data = read_checkpoint(path)
    assert data["posts_seen"] == 3
    assert data["last_post_url"] == "https://linkedin.com/posts/3"
    assert "updated_at" in data


def test_read_missing_checkpoint_returns_none(tmp_path):
    assert read_checkpoint(tmp_path / "no-such-file.json") is None


def test_write_overwrites_previous_checkpoint(tmp_path):
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, posts_seen=1, last_post_url="https://linkedin.com/posts/1")
    write_checkpoint(path, posts_seen=2, last_post_url="https://linkedin.com/posts/2")

    data = read_checkpoint(path)
    assert data["posts_seen"] == 2
    assert data["last_post_url"] == "https://linkedin.com/posts/2"
