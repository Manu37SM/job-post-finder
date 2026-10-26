"""
Hiring-signal and company detection.

Recruiter identity (name/headline) is NOT extracted from post text at all -
it comes straight from RawPost.author_name/author_headline, which LinkedIn
already tells us. Guessing a recruiter's name out of post text would violate
the "never invent a name" rule in the spec, so there is no such function
here on purpose.

Company extraction is best-effort and conservative: it only returns a value
when a clear company-suffix pattern (Technologies, Pvt Ltd, LLP, Inc, ...)
is present in the text. No suffix match -> None (UNKNOWN), never a guess at
a bare capitalized word.
"""

import re

HIRING_PHRASES = (
    "hiring",
    "we're hiring",
    "we are hiring",
    "open position",
    "opening",
    "immediate opening",
    "looking for",
    "recruitment",
    "walk-in",
    "send cv",
    "send resume",
    "dm me",
    "contact",
    "apply",
    "vacancy",
    "job opening",
)

_COMPANY_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z&.,\-]*(?:\s+[A-Z][A-Za-z&.,\-]*){0,4}\s+"
    r"(?:Technologies|Pvt\.?\s*Ltd\.?|LLP|Inc\.?|Ltd\.?|Solutions|Consulting|Systems|Corp\.?|Labs))\b"
)

# Sentence-initial capitalized words that can legitimately chain into the
# regex above (e.g. "Join ABC Technologies Pvt Ltd") but aren't part of the
# company name themselves.
_LEADING_STOPWORDS = {
    "join", "hiring", "we", "we're", "urgent", "looking", "opening",
    "apply", "send", "contact", "immediate", "walk-in", "the", "a", "an",
}


def detect_hiring_signal(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(phrase in lowered for phrase in HIRING_PHRASES)


def extract_company(text: str) -> str | None:
    """Only matches a clear company-suffix pattern - never guesses a bare name."""
    if not text:
        return None
    match = _COMPANY_SUFFIX_RE.search(text)
    if not match:
        return None
    words = match.group(1).split()
    while words and words[0].lower().strip(".,") in _LEADING_STOPWORDS:
        words.pop(0)
    return " ".join(words) if words else None
