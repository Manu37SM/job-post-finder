"""
Entry point wiring: post source -> pipeline.process_post -> db.upsert -> logs
-> exports.

Uses linkedin/fixture_source.py as the post source for now (see that
module's docstring) - swapping in the real Playwright source later is a
one-line change in main(), since run_pipeline() takes a `discover_fn`
callable rather than importing a source itself.

DRY RUN: this project never sends email itself - that's the existing
mass-mailer's job, run separately, after human review. So there is no
"send" step here for --dry-run to gate in the sense the spec's other
projects use it. To keep the flag meaningful anyway (and as an extra safety
margin beyond the human-review gate), --dry-run additionally skips writing
data/approved_recruiters.xlsx (the file that feeds the mailer) even if some
records are already APPROVED from a prior review session. Discovery,
extraction, filtering, dedup, and the three general-purpose exports
(xlsx/csv/txt) all run either way, since none of them send or approve
anything.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

from config import Config
from core.models import RecordStatus
from export.csv import export_csv
from export.excel import export_excel
from export.mailer_adapter import export_approved_for_mailer
from export.text import export_text
from linkedin.fixture_source import discover_posts
from ocr.engine import get_ocr_provider, is_worth_ocr
from pipeline import process_post
from storage.checkpoint import write_checkpoint
from storage.database import Database
from storage.run_logs import log_discovery, log_failed, log_ocr_failure, log_skipped, log_success


@dataclass
class RunSummary:
    posts_discovered: int = 0
    posts_processed: int = 0
    posts_failed: int = 0
    images_found: int = 0
    images_processed: int = 0
    ocr_successes: int = 0
    ocr_failures: int = 0
    emails_found: int = 0
    roles_found: int = 0
    mumbai_matches: int = 0
    remote_matches: int = 0
    rejected_locations: int = 0
    excluded: int = 0
    duplicates: int = 0
    records_requiring_review: int = 0
    review_without_email: int = 0

    def print_report(self, print_fn=print) -> None:
        print_fn(f"Posts discovered:         {self.posts_discovered}")
        print_fn(f"Posts processed:          {self.posts_processed}")
        print_fn(f"Posts failed:             {self.posts_failed}")
        print_fn(f"Images found:             {self.images_found}")
        print_fn(f"Images processed:         {self.images_processed}")
        print_fn(f"OCR successes:            {self.ocr_successes}")
        print_fn(f"OCR failures:             {self.ocr_failures}")
        print_fn(f"Emails found:             {self.emails_found}")
        print_fn(f"Roles found:              {self.roles_found}")
        print_fn(f"Mumbai matches:           {self.mumbai_matches}")
        print_fn(f"Remote matches:           {self.remote_matches}")
        print_fn(f"Rejected locations:       {self.rejected_locations}")
        print_fn(f"Excluded (false positive): {self.excluded}")
        print_fn(f"Duplicates:               {self.duplicates}")
        print_fn(f"Records requiring review: {self.records_requiring_review}")
        print_fn(f"  ...of which no email:   {self.review_without_email}")


def run_pipeline(
    config: Config,
    db: Database,
    discover_fn=discover_posts,
    discover_arg: str | Path = "data/sample_posts.json",
    checkpoint_path: str | Path = "checkpoint.json",
    logs_dir: str | Path = "logs",
    data_dir: str | Path = "data",
    dry_run: bool | None = None,
    should_stop=None,
) -> RunSummary:
    """should_stop: optional zero-arg callable polled between posts; when it
    returns True the run ends cleanly with the progress made so far (the GUI's
    Stop button used to be a request flag that nothing ever read)."""
    dry_run = config.dry_run if dry_run is None else dry_run
    logs_dir = Path(logs_dir)
    data_dir = Path(data_dir)

    discovery_log = logs_dir / "discovery.log"
    success_log = logs_dir / "success.csv"
    failed_log = logs_dir / "failed.csv"
    skipped_log = logs_dir / "skipped.csv"
    ocr_failures_log = logs_dir / "ocr-failures.csv"

    ocr_provider = get_ocr_provider(config.ocr_provider, tesseract_cmd=config.tesseract_cmd)
    summary = RunSummary()

    raw_posts = discover_fn(
        discover_arg,
        config.search_terms,
        config.max_posts,
        max_scrolls=config.max_scrolls,
        scroll_pause_seconds=config.scroll_pause_seconds,
    )
    summary.posts_discovered = len(raw_posts)
    log_discovery(discovery_log, f"Discovered {len(raw_posts)} posts")

    already_seen = db.seen_post_urls()

    for raw in raw_posts:
        if should_stop is not None and should_stop():
            log_discovery(discovery_log, "Stop requested - ending run early")
            break
        if raw.post_url in already_seen:
            log_discovery(discovery_log, f"Resuming: skipping already-processed {raw.post_url}")
            continue

        try:
            # Stub source treats image_urls entries as local paths directly -
            # a real scraper would download first and build this mapping.
            image_downloads = {url: url for url in raw.image_urls}
            summary.images_found += len(image_downloads)
            worth_ocr = [p for p in image_downloads.values() if is_worth_ocr(p)]
            summary.images_processed += len(worth_ocr)

            record, ocr_failures = process_post(
                raw, config, db, image_downloads=image_downloads, ocr_provider=ocr_provider
            )
            db.upsert(record)

            summary.ocr_failures += len(ocr_failures)
            summary.ocr_successes += max(0, len(worth_ocr) - len(ocr_failures))
            for failure in ocr_failures:
                log_ocr_failure(
                    ocr_failures_log,
                    failure.post_url,
                    failure.image_url,
                    failure.error,
                    failure.timestamp,
                )

            if record.extracted.primary_email:
                summary.emails_found += 1
            if record.extracted.job_role:
                summary.roles_found += 1

            if record.location_match_reason == "MUMBAI_MATCH":
                summary.mumbai_matches += 1
            elif record.location_match_reason == "EXPLICIT_REMOTE":
                summary.remote_matches += 1

            if record.excluded:
                summary.excluded += 1
                log_skipped(skipped_log, raw.post_url, f"excluded:{record.exclusion_reason}")
            elif not record.location_match:
                summary.rejected_locations += 1
                log_skipped(skipped_log, raw.post_url, f"location:{record.location_rejection_reason}")
            elif record.duplicate_of:
                summary.duplicates += 1
                log_skipped(skipped_log, raw.post_url, f"duplicate:{record.duplicate_reason}")
            elif record.status == RecordStatus.SKIPPED:
                log_skipped(skipped_log, raw.post_url, "below_minimum_relevance_score")
            else:
                summary.records_requiring_review += 1
                if not record.extracted.primary_email:
                    summary.review_without_email += 1
                log_success(success_log, raw.post_url, record.status.value)

            summary.posts_processed += 1

        except Exception as e:  # never let one bad post crash the whole run
            summary.posts_failed += 1
            log_failed(failed_log, raw.post_url, str(e))
            log_discovery(discovery_log, f"FAILED processing {raw.post_url}: {e}")

        write_checkpoint(checkpoint_path, summary.posts_processed, raw.post_url)

    all_records = db.all_records()
    export_excel(all_records, data_dir / "linkedin_recruiters.xlsx")
    export_csv(all_records, data_dir / "linkedin_recruiters.csv")
    export_text(all_records, data_dir / "linkedin_recruiters.txt")

    if not dry_run:
        approved = [r for r in all_records if r.status == RecordStatus.APPROVED]
        export_approved_for_mailer(approved, data_dir / "approved_recruiters.xlsx")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="LinkedIn Recruiter Post Finder")
    parser.add_argument("--config", default="config.json")
    parser.add_argument(
        "--fixture",
        default="data/sample_posts.json",
        help="Path to a RawPost-shaped JSON fixture (used unless --live is passed)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Use the real Playwright LinkedIn source (linkedin/search.py) instead of "
            "the JSON fixture. Requires `playwright install chromium` and a session "
            "saved via linkedin.session.save_session() first - see README."
        ),
    )
    parser.add_argument(
        "--session",
        default="session-linkedin.json",
        help="Path to the saved LinkedIn session (only used with --live)",
    )
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "--dry-run skips writing approved_recruiters.xlsx even if some records "
            "are already APPROVED; --no-dry-run forces writing it. Omit either flag "
            "to use config.json's \"dry_run\" value (true by default)."
        ),
    )
    parser.add_argument("--review", action="store_true", help="Run the CLI review session after processing")
    args = parser.parse_args()

    config = Config.load(args.config)
    db = Database("data/linkedin_recruiters.db")

    if args.live:
        from linkedin.search import discover_posts as discover_fn

        discover_arg = args.session
    else:
        discover_fn = discover_posts
        discover_arg = args.fixture

    try:
        summary = run_pipeline(
            config, db, discover_fn=discover_fn, discover_arg=discover_arg, dry_run=args.dry_run
        )
        summary.print_report()

        if args.review:
            from review.reviewer import run_review_session

            counts = run_review_session(db)
            print(f"\nReview complete: {counts}")

            effective_dry_run = args.dry_run if args.dry_run is not None else config.dry_run
            if not effective_dry_run:
                approved = [r for r in db.all_records() if r.status == RecordStatus.APPROVED]
                export_approved_for_mailer(approved)
                print(f"Exported {len(approved)} approved record(s) to data/approved_recruiters.xlsx")
    finally:
        db.close()


if __name__ == "__main__":
    main()
