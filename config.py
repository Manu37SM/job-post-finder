"""
Loads config.json the same way mass-mailer does: a plain JSON file, copied by
the user from config.example.json, never committed. See config.example.json
for the documented shape.
"""

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_MUMBAI_ALIASES = ["Mumbai", "Bombay", "Mumbai Metropolitan Region", "MMR"]

DEFAULT_REMOTE_TERMS = [
    "Remote",
    "Fully Remote",
    "Remote - India",
    "India Remote",
    "Work From Home",
    "WFH",
    "Remote anywhere in India",
]


@dataclass
class Config:
    search_terms: list[str] = field(default_factory=list)

    accepted_location: str = "Mumbai"
    accepted_location_aliases: list[str] = field(
        default_factory=lambda: list(DEFAULT_MUMBAI_ALIASES)
    )
    accepted_remote_terms: list[str] = field(
        default_factory=lambda: list(DEFAULT_REMOTE_TERMS)
    )

    target_roles: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)

    ocr_provider: str = "tesseract"
    # Full path to the Tesseract binary. Leave null to auto-detect (PATH,
    # then common Windows install locations) - see
    # ocr/tesseract.py's module docstring for why Windows often needs this
    # set explicitly even after installing Tesseract.
    tesseract_cmd: str | None = None

    # pHash Hamming distance below which two post images are treated as the
    # same graphic for dedup purposes (0 = identical, 64 = maximally
    # different for a standard 64-bit pHash). 8 is a commonly-used
    # near-duplicate threshold for pHash; lower is stricter.
    image_hash_max_distance: int = 8

    max_posts: int = 100
    # How deep to scroll each search term's results (live source only).
    # Higher = more posts discovered per term, but a slower run and more
    # automated-looking traffic to LinkedIn. Scrolling stops early on its
    # own once the feed stops yielding new posts, so a generous ceiling
    # only costs time when there really are more results to find.
    max_scrolls: int = 15
    scroll_pause_seconds: float = 1.5
    minimum_relevance_score: int = 0
    deduplicate: bool = True
    review_required: bool = True
    dry_run: bool = True

    @classmethod
    def load(cls, path: str | Path = "config.json") -> "Config":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Copy config.example.json to config.json "
                "and fill in your own values first."
            )
        raw = json.loads(path.read_text())
        known_fields = {f.name for f in fields(cls)}
        unknown = set(raw) - known_fields
        if unknown:
            # Fail loud rather than silently ignoring a typo'd config key.
            raise ValueError(f"Unknown config key(s) in {path}: {sorted(unknown)}")
        return cls(**raw)
