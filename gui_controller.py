"""
Pure application logic behind the Tkinter GUI (gui.py) - deliberately
Tkinter-free so it's fully unit-testable without a display. gui.py is a
thin shell: it creates a GuiController, wires widget callbacks to its
methods, and renders whatever they return. gui.py itself can't be
meaningfully unit-tested in this environment (no display - see README
"Current limitations"), so keeping all real logic here, tested, is what
makes the GUI trustworthy despite that.
"""

import json
import threading
from dataclasses import dataclass
from pathlib import Path

from app import RunSummary, run_pipeline
from config import Config
from core.models import RecordStatus
from export.mailer_adapter import export_approved_for_mailer
from linkedin.fixture_source import discover_posts as discover_posts_fixture
from review.reviewer import apply_decision, format_for_review, get_review_queue
from storage.database import Database


@dataclass
class ReviewRow:
    """One row for the GUI's review table - plain data, no widget references."""

    post_url: str
    company: str
    job_role: str
    job_location: str
    work_mode: str
    email: str


class GuiController:
    """
    One instance per running GUI session. Owns the Config and Database
    (opened lazily so gui.py controls when paths are resolved), and exposes
    plain methods gui.py's button callbacks call directly.

    Threading: LinkedIn/OCR calls are blocking, so start_run_async() runs
    run_pipeline() on a background daemon thread and delivers the result via
    the on_done/on_error callbacks gui.py provides - mirroring mass-mailer's
    own gui.py Run tab (background worker + live log). gui.py is responsible
    for marshalling those callbacks back onto the Tkinter main thread (e.g.
    via root.after()), same as any Tkinter app doing background work.

    Stop button: request_stop() sets a threading.Event, but run_pipeline()
    does not currently check it mid-post - that would need a small hook
    added to pipeline.py's per-post loop. Today, Stop is a "finish the
    current post, then don't start the next search term" request at best;
    documenting this honestly rather than implying instant cancellation.
    """

    def __init__(
        self,
        config_path: str | Path = "config.json",
        db_path: str | Path = "data/linkedin_recruiters.db",
        data_dir: str | Path = "data",
        logs_dir: str | Path = "logs",
        checkpoint_path: str | Path = "checkpoint.json",
    ):
        self.config_path = Path(config_path)
        self.db_path = Path(db_path)
        # These three default to the same literals run_pipeline() itself
        # defaults to, but MUST be threaded through explicitly in start_run()
        # below - relying on run_pipeline()'s own defaults here would silently
        # write to the process's actual CWD regardless of where db_path/
        # config_path point, which is exactly the bug this constructor
        # parameter set exists to prevent (caught via real writes landing in
        # the repo root during testing, before this fix).
        self.data_dir = Path(data_dir)
        self.logs_dir = Path(logs_dir)
        self.checkpoint_path = Path(checkpoint_path)
        self.config: Config | None = None
        self.db: Database | None = None
        self._stop_event = threading.Event()

    # ---- Config ----

    def load_config(self) -> Config:
        self.config = Config.load(self.config_path)
        return self.config

    def save_config(self, **overrides) -> Config:
        """Merges overrides into the current config and writes it back to
        config.json as plain JSON - mirrors mass-mailer's Config tab save."""
        if self.config is None:
            self.load_config()
        data = {**self.config.__dict__, **overrides}
        self.config = Config(**data)
        self.config_path.write_text(json.dumps(data, indent=4))
        return self.config

    # ---- Database ----

    def open_database(self) -> Database:
        self.db = Database(self.db_path)
        return self.db

    def close_database(self) -> None:
        if self.db is not None:
            self.db.close()
            self.db = None

    # ---- Run ----

    def request_stop(self) -> None:
        self._stop_event.set()

    def run_stopped(self) -> bool:
        return self._stop_event.is_set()

    def start_run(
        self,
        discover_arg,
        discover_fn=discover_posts_fixture,
        dry_run: bool | None = None,
    ) -> RunSummary:
        """
        Synchronous. gui.py calls this from a background thread (see
        start_run_async) so the UI doesn't freeze; tests call it directly
        on the main thread.
        """
        if self.config is None:
            self.load_config()
        if self.db is None:
            self.open_database()
        self._stop_event.clear()
        return run_pipeline(
            self.config,
            self.db,
            discover_fn=discover_fn,
            discover_arg=discover_arg,
            checkpoint_path=self.checkpoint_path,
            logs_dir=self.logs_dir,
            data_dir=self.data_dir,
            dry_run=dry_run,
            should_stop=self._stop_event.is_set,
        )

    def start_run_async(
        self,
        discover_arg,
        discover_fn=discover_posts_fixture,
        dry_run=None,
        on_done=None,
        on_error=None,
    ) -> threading.Thread:
        """Fire-and-forget: runs start_run() on a daemon thread."""

        def _worker():
            try:
                summary = self.start_run(discover_arg, discover_fn=discover_fn, dry_run=dry_run)
                if on_done:
                    on_done(summary)
            except Exception as e:  # noqa: BLE001 - report to caller, don't crash the thread silently
                if on_error:
                    on_error(e)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return thread

    # ---- Review ----

    def get_review_rows(self) -> list[ReviewRow]:
        if self.db is None:
            self.open_database()
        rows = []
        for record in get_review_queue(self.db):
            ep = record.extracted
            rows.append(
                ReviewRow(
                    post_url=ep.raw.post_url,
                    company=ep.company or "UNKNOWN",
                    job_role=ep.job_role or "UNKNOWN",
                    job_location=ep.job_location or "UNKNOWN",
                    work_mode=ep.work_mode.value,
                    email=ep.primary_email or "UNKNOWN",
                )
            )
        return rows

    def get_review_detail(self, post_url: str) -> str | None:
        if self.db is None:
            self.open_database()
        record = self.db.get_by_post_url(post_url)
        return format_for_review(record) if record else None

    def decide(self, post_url: str, choice: str) -> RecordStatus:
        if self.db is None:
            self.open_database()
        record = self.db.get_by_post_url(post_url)
        if record is None:
            raise ValueError(f"No record found for {post_url}")
        return apply_decision(record, choice, self.db)

    # ---- Export ----

    def export_for_mailer(self, path: str | Path | None = None) -> tuple[Path, int]:
        """Defaults to <self.data_dir>/approved_recruiters.xlsx - a literal
        default here would have the same CWD-leakage bug start_run() had
        before its fix (see __init__'s comment)."""
        if path is None:
            path = self.data_dir / "approved_recruiters.xlsx"
        if self.db is None:
            self.open_database()
        approved = [r for r in self.db.all_records() if r.status == RecordStatus.APPROVED]
        out_path = export_approved_for_mailer(approved, path)
        return out_path, len(approved)

    def status_counts(self) -> dict[str, int]:
        if self.db is None:
            self.open_database()
        counts: dict[str, int] = {}
        for record in self.db.all_records():
            counts[record.status.value] = counts.get(record.status.value, 0) + 1
        return counts
