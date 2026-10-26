"""
checkpoint.json - a small human-readable status marker, per spec.

The actual resume mechanism is the SQLite `records` table itself
(Database.seen_post_urls()) - it's already persistent and already indexed,
so re-deriving the same "what's done" information into a second file would
just risk the two going out of sync after a crash. checkpoint.json here is
a status summary for a human glancing at the file (or a future GUI), not
something the pipeline reads back to decide what to skip.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def write_checkpoint(path: str | Path, posts_seen: int, last_post_url: str | None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "posts_seen": posts_seen,
        "last_post_url": last_post_url,
    }
    path.write_text(json.dumps(data, indent=2))


def read_checkpoint(path: str | Path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text())
