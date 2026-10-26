import json
import threading

import openpyxl
import pytest

from config import Config
from core.models import RecordStatus
from gui_controller import GuiController
from linkedin.fixture_source import discover_posts


def _write_fixture(path, posts):
    path.write_text(json.dumps(posts))
    return path


def _write_config(path, **overrides):
    data = {
        "target_roles": ["Java Developer"],
        "exclude_keywords": ["bootcamp"],
        "accepted_location_aliases": ["Mumbai", "Bombay", "MMR"],
        "accepted_remote_terms": ["Remote"],
    }
    data.update(overrides)
    path.write_text(json.dumps(data))
    return path


def _make_controller(tmp_path, **config_overrides):
    """Every GuiController in these tests must isolate ALL its file outputs
    under tmp_path - config, db, AND data/logs/checkpoint. Missing the
    latter three here is exactly the bug that let real files (checkpoint.json,
    data/linkedin_recruiters.*) leak into the project root during testing
    before gui_controller.py's start_run()/export_for_mailer() were fixed to
    forward these paths instead of relying on run_pipeline()'s own CWD-relative
    defaults. This single factory is what makes that mistake hard to repeat."""
    config_path = _write_config(tmp_path / "config.json", **config_overrides)
    return GuiController(
        config_path=config_path,
        db_path=tmp_path / "test.db",
        data_dir=tmp_path / "data",
        logs_dir=tmp_path / "logs",
        checkpoint_path=tmp_path / "checkpoint.json",
    )


# ---- Config ----


def test_load_config(tmp_path):
    controller = _make_controller(tmp_path)
    config = controller.load_config()
    assert config.target_roles == ["Java Developer"]


def test_save_config_merges_overrides_and_persists(tmp_path):
    controller = _make_controller(tmp_path)
    config_path = controller.config_path
    controller.load_config()

    updated = controller.save_config(max_posts=50, dry_run=False)
    assert updated.max_posts == 50
    assert updated.dry_run is False

    reloaded = Config.load(config_path)
    assert reloaded.max_posts == 50
    assert reloaded.dry_run is False


def test_save_config_without_prior_load(tmp_path):
    controller = _make_controller(tmp_path)
    updated = controller.save_config(max_posts=25)
    assert updated.max_posts == 25


# ---- Database lifecycle ----


def test_open_and_close_database(tmp_path):
    controller = _make_controller(tmp_path)
    db = controller.open_database()
    assert controller.db is db
    controller.close_database()
    assert controller.db is None


# ---- Run ----


def test_start_run_sync(tmp_path):
    fixture = _write_fixture(
        tmp_path / "posts.json",
        [
            {
                "post_url": "https://linkedin.com/posts/1",
                "post_text": "Hiring Java Developer\nLocation: Mumbai\njobs@example.com",
            }
        ],
    )
    controller = _make_controller(tmp_path)
    summary = controller.start_run(
        discover_arg=fixture,
        discover_fn=discover_posts,
    )
    assert summary.posts_discovered == 1
    assert summary.records_requiring_review == 1
    assert controller.status_counts() == {"NEW": 1}


def test_start_run_async_calls_on_done(tmp_path):
    fixture = _write_fixture(
        tmp_path / "posts.json",
        [{"post_url": "https://linkedin.com/posts/1", "post_text": "Hiring Java Developer - Mumbai"}],
    )
    controller = _make_controller(tmp_path)

    done_event = threading.Event()
    results = {}

    def on_done(summary):
        results["summary"] = summary
        done_event.set()

    thread = controller.start_run_async(
        discover_arg=fixture, discover_fn=discover_posts, on_done=on_done
    )
    thread.join(timeout=5)
    assert done_event.wait(timeout=1)
    assert results["summary"].posts_discovered == 1


def test_start_run_async_calls_on_error_for_missing_fixture(tmp_path):
    controller = _make_controller(tmp_path)

    error_event = threading.Event()
    results = {}

    def on_error(exc):
        results["error"] = exc
        error_event.set()

    thread = controller.start_run_async(
        discover_arg=tmp_path / "does-not-exist.json",
        discover_fn=discover_posts,
        on_error=on_error,
    )
    thread.join(timeout=5)
    assert error_event.wait(timeout=1)
    assert isinstance(results["error"], FileNotFoundError)


def test_request_stop_and_run_stopped(tmp_path):
    controller = _make_controller(tmp_path)
    assert controller.run_stopped() is False
    controller.request_stop()
    assert controller.run_stopped() is True


# ---- Review ----


def test_get_review_rows_only_new(tmp_path):
    fixture = _write_fixture(
        tmp_path / "posts.json",
        [
            {"post_url": "https://linkedin.com/posts/1", "post_text": "Hiring Java Developer - Mumbai - jobs@example.com"},
            {"post_url": "https://linkedin.com/posts/2", "post_text": "Hiring Java Developer - Pune"},
        ],
    )
    controller = _make_controller(tmp_path)
    controller.start_run(discover_arg=fixture, discover_fn=discover_posts)

    rows = controller.get_review_rows()
    assert len(rows) == 1
    assert rows[0].post_url == "https://linkedin.com/posts/1"
    assert rows[0].job_location == "Mumbai"
    assert rows[0].email == "jobs@example.com"


def test_get_review_detail(tmp_path):
    fixture = _write_fixture(
        tmp_path / "posts.json",
        [{"post_url": "https://linkedin.com/posts/1", "post_text": "Hiring Java Developer - Mumbai - jobs@example.com"}],
    )
    controller = _make_controller(tmp_path)
    controller.start_run(discover_arg=fixture, discover_fn=discover_posts)

    detail = controller.get_review_detail("https://linkedin.com/posts/1")
    assert "jobs@example.com" in detail
    assert controller.get_review_detail("https://linkedin.com/posts/missing") is None


def test_decide_updates_status(tmp_path):
    fixture = _write_fixture(
        tmp_path / "posts.json",
        [{"post_url": "https://linkedin.com/posts/1", "post_text": "Hiring Java Developer - Mumbai - jobs@example.com"}],
    )
    controller = _make_controller(tmp_path)
    controller.start_run(discover_arg=fixture, discover_fn=discover_posts)

    status = controller.decide("https://linkedin.com/posts/1", "A")
    assert status == RecordStatus.APPROVED
    assert controller.status_counts() == {"APPROVED": 1}


def test_decide_unknown_post_url_raises(tmp_path):
    controller = _make_controller(tmp_path)
    controller.open_database()
    with pytest.raises(ValueError):
        controller.decide("https://linkedin.com/posts/nope", "A")


# ---- Export ----


def test_export_for_mailer_only_approved(tmp_path):
    fixture = _write_fixture(
        tmp_path / "posts.json",
        [{"post_url": "https://linkedin.com/posts/1", "post_text": "Hiring Java Developer - Mumbai - jobs@example.com"}],
    )
    controller = _make_controller(tmp_path)
    controller.start_run(discover_arg=fixture, discover_fn=discover_posts)
    controller.decide("https://linkedin.com/posts/1", "A")

    out_path, count = controller.export_for_mailer(tmp_path / "approved.xlsx")
    assert count == 1
    wb = openpyxl.load_workbook(out_path)
    rows = list(wb.active.iter_rows(min_row=2, values_only=True))
    assert rows[0][1] == "jobs@example.com"


def test_status_counts_tallies_all_statuses(tmp_path):
    fixture = _write_fixture(
        tmp_path / "posts.json",
        [
            {"post_url": "https://linkedin.com/posts/1", "post_text": "Hiring Java Developer - Mumbai - jobs@example.com"},
            {"post_url": "https://linkedin.com/posts/2", "post_text": "Hiring Java Developer - Pune"},
        ],
    )
    controller = _make_controller(tmp_path)
    controller.start_run(discover_arg=fixture, discover_fn=discover_posts)
    counts = controller.status_counts()
    assert counts == {"NEW": 1, "SKIPPED": 1}
