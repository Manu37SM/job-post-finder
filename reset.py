"""
Deletes every generated artifact (database, exports, logs, checkpoint,
downloaded images, debug captures) so the next run starts completely
fresh - without touching the things that are expensive or annoying to
redo: config.json, session-linkedin.json, and data/sample_posts.json.

Usage:
    python reset.py            # asks for confirmation first
    python reset.py --yes      # skips the confirmation prompt
"""

import argparse
import shutil
from pathlib import Path

# Single files to delete if present.
FILES_TO_DELETE = [
    "checkpoint.json",
    "data/linkedin_recruiters.db",
    "data/linkedin_recruiters.xlsx",
    "data/linkedin_recruiters.csv",
    "data/linkedin_recruiters.txt",
    "data/approved_recruiters.xlsx",
]

# Whole directories to delete (and their contents) if present.
DIRS_TO_DELETE = [
    "data/downloaded_images",
    "data/debug",
]

# Glob patterns, relative to project root, for logs (keeps logs/.gitkeep).
LOG_PATTERNS = ["logs/*.log", "logs/*.csv"]

# Explicitly NOT touched, listed here so it's obvious at a glance:
#   config.json              - your settings
#   session-linkedin.json    - your LinkedIn login, expensive to redo
#   data/sample_posts.json   - the demo fixture, not generated
#   data/.gitkeep, logs/.gitkeep


def find_targets(root: Path) -> tuple[list[Path], list[Path]]:
    """Returns (files_found, dirs_found) - only paths that actually exist."""
    files = [root / f for f in FILES_TO_DELETE if (root / f).exists()]
    for pattern in LOG_PATTERNS:
        files.extend(root.glob(pattern))
    dirs = [root / d for d in DIRS_TO_DELETE if (root / d).exists()]
    return files, dirs


def reset(root: str | Path = ".", confirm: bool = True, print_fn=print) -> int:
    """Returns the number of items (files + dirs) deleted."""
    root = Path(root)
    files, dirs = find_targets(root)

    if not files and not dirs:
        print_fn("Nothing to clean up - already fresh.")
        return 0

    print_fn("This will permanently delete:")
    for f in files:
        print_fn(f"  file: {f}")
    for d in dirs:
        print_fn(f"  dir:  {d}/")
    print_fn(
        "\nNOT touched: config.json, session-linkedin.json, "
        "data/sample_posts.json"
    )

    if confirm:
        answer = input("\nProceed? [y/N]: ").strip().lower()
        if answer != "y":
            print_fn("Cancelled - nothing deleted.")
            return 0

    count = 0
    for f in files:
        f.unlink(missing_ok=True)
        count += 1
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)
        count += 1

    print_fn(f"\nDeleted {count} item(s). Starting fresh on the next run.")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up all generated LinkedInRecruiterFinder output")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()
    reset(confirm=not args.yes)


if __name__ == "__main__":
    main()
