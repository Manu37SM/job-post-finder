from pathlib import Path

from reset import find_targets, reset


def _make_fake_project(root: Path) -> None:
    (root / "data").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)

    # Generated artifacts - should all get deleted.
    (root / "checkpoint.json").write_text("{}")
    (root / "data" / "linkedin_recruiters.db").write_bytes(b"")
    (root / "data" / "linkedin_recruiters.xlsx").write_bytes(b"")
    (root / "data" / "linkedin_recruiters.csv").write_text("")
    (root / "data" / "linkedin_recruiters.txt").write_text("")
    (root / "data" / "approved_recruiters.xlsx").write_bytes(b"")
    (root / "data" / "downloaded_images").mkdir()
    (root / "data" / "downloaded_images" / "img1.jpg").write_bytes(b"x")
    (root / "data" / "debug").mkdir()
    (root / "data" / "debug" / "Java_Developer.png").write_bytes(b"x")
    (root / "data" / "debug" / "Java_Developer.html").write_text("<html></html>")
    (root / "logs" / "discovery.log").write_text("log line\n")
    (root / "logs" / "success.csv").write_text("post_url\n")
    (root / "logs" / "skipped.csv").write_text("post_url\n")

    # Precious files - must NOT be deleted.
    (root / "config.json").write_text("{}")
    (root / "session-linkedin.json").write_text("{}")
    (root / "data" / "sample_posts.json").write_text("[]")
    (root / "data" / ".gitkeep").write_text("")
    (root / "logs" / ".gitkeep").write_text("")


def test_find_targets_identifies_only_generated_files(tmp_path):
    _make_fake_project(tmp_path)
    files, dirs = find_targets(tmp_path)

    file_names = {f.name for f in files}
    assert file_names == {
        "checkpoint.json",
        "linkedin_recruiters.db",
        "linkedin_recruiters.xlsx",
        "linkedin_recruiters.csv",
        "linkedin_recruiters.txt",
        "approved_recruiters.xlsx",
        "discovery.log",
        "success.csv",
        "skipped.csv",
    }
    dir_names = {d.name for d in dirs}
    assert dir_names == {"downloaded_images", "debug"}


def test_find_targets_on_already_clean_project(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "data" / "sample_posts.json").write_text("[]")

    files, dirs = find_targets(tmp_path)
    assert files == []
    assert dirs == []


def test_reset_deletes_generated_files_and_dirs(tmp_path):
    _make_fake_project(tmp_path)
    printed = []
    count = reset(root=tmp_path, confirm=False, print_fn=printed.append)

    assert count == 11  # 9 files + 2 dirs
    assert not (tmp_path / "checkpoint.json").exists()
    assert not (tmp_path / "data" / "linkedin_recruiters.db").exists()
    assert not (tmp_path / "data" / "downloaded_images").exists()
    assert not (tmp_path / "data" / "debug").exists()
    assert not (tmp_path / "logs" / "discovery.log").exists()


def test_reset_preserves_precious_files(tmp_path):
    _make_fake_project(tmp_path)
    reset(root=tmp_path, confirm=False, print_fn=lambda _: None)

    assert (tmp_path / "config.json").exists()
    assert (tmp_path / "session-linkedin.json").exists()
    assert (tmp_path / "data" / "sample_posts.json").exists()
    assert (tmp_path / "data" / ".gitkeep").exists()
    assert (tmp_path / "logs" / ".gitkeep").exists()


def test_reset_on_already_clean_project_reports_nothing_to_do(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    printed = []
    count = reset(root=tmp_path, confirm=False, print_fn=printed.append)

    assert count == 0
    assert any("Nothing to clean up" in line for line in printed)


def test_reset_respects_confirmation_prompt_decline(tmp_path, monkeypatch):
    _make_fake_project(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "n")

    count = reset(root=tmp_path, confirm=True, print_fn=lambda _: None)

    assert count == 0
    assert (tmp_path / "checkpoint.json").exists()  # nothing deleted


def test_reset_confirmation_prompt_accept(tmp_path, monkeypatch):
    _make_fake_project(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "y")

    count = reset(root=tmp_path, confirm=True, print_fn=lambda _: None)

    assert count == 11
    assert not (tmp_path / "checkpoint.json").exists()
