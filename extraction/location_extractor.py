"""
Best-effort location + work-mode extraction. This is the least reliable
extractor in the pipeline (see project README, "Limitations") because it's
doing text-proximity heuristics, not real NLP - it will misfire on unusual
phrasing. It never guesses: no match means None/UNKNOWN, and the filtering
layer rejects unknown locations rather than assuming remote.

Design:
  1. An explicit "Location:" / "Job Location:" labeled line is the strongest
     signal and wins outright.
  2. Otherwise, scan for known city names and drop any mention that sits right
     after a company-HQ phrase ("headquartered in", "based out of", ...) so a
     post like "HQ in Bangalore, hiring for Mumbai" doesn't extract Bangalore.
  3. Work mode is extracted separately from the same combined text - remote
     terms are configurable (see config.py) because that's what the product
     spec calls for; onsite/hybrid keywords are fixed, they're not something
     the user asked to reconfigure.
"""

import re

from core.models import Confidence, WorkMode

_LOCATION_LABEL_RE = re.compile(
    r"(?:job\s+)?(?:work\s+)?location\s*[:\-]\s*([^\n\r]+)", re.IGNORECASE
)

_HQ_SIGNAL_PHRASES = (
    "headquartered in",
    "headquartered at",
    "head office in",
    "head office at",
    "hq in",
    "hq at",
    "based out of",
    "corporate office in",
    "registered office in",
)

# Not exhaustive - a practical set covering the cities this project's own spec
# uses as examples. Extend freely; it only decides *that* a location string
# was found, not whether it counts as Mumbai (that's config-driven, see
# filtering/location.py).
DEFAULT_KNOWN_CITIES = [
    "Mumbai",
    "Bombay",
    "Mumbai Metropolitan Region",
    "Navi Mumbai",
    "Thane",
    "Bangalore",
    "Bengaluru",
    "Pune",
    "Hyderabad",
    "Chennai",
    "Delhi",
    "New Delhi",
    "Noida",
    "Gurugram",
    "Gurgaon",
    "Ahmedabad",
    "Kolkata",
    "Jaipur",
    "Nagpur",
    "Nashik",
    "Kochi",
    "Coimbatore",
    "Indore",
    "Chandigarh",
]

_HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
_ONSITE_RE = re.compile(r"\b(on[\s\-]?site|work from office|wfo)\b", re.IGNORECASE)


def extract_location(
    text: str, known_cities: list[str] | None = None
) -> tuple[str | None, Confidence]:
    """Returns (job_location_string, confidence). None/NONE if nothing usable found."""
    if not text:
        return None, Confidence.NONE

    labeled = _LOCATION_LABEL_RE.search(text)
    if labeled:
        value = labeled.group(1).strip(" .\t")
        value = re.split(r"[|\u2022]", value)[0].strip()
        if value:
            return value, Confidence.HIGH

    cities = known_cities if known_cities is not None else DEFAULT_KNOWN_CITIES
    lowered = text.lower()
    candidates: list[tuple[str, int, bool]] = []
    for city in cities:
        for match in re.finditer(r"\b" + re.escape(city.lower()) + r"\b", lowered):
            preceding = lowered[max(0, match.start() - 40) : match.start()]
            is_hq_context = any(sig in preceding for sig in _HQ_SIGNAL_PHRASES)
            candidates.append((city, match.start(), is_hq_context))

    non_hq = [c for c in candidates if not c[2]]
    if non_hq:
        non_hq.sort(key=lambda c: c[1])  # earliest mention that isn't HQ context
        return non_hq[0][0], Confidence.MEDIUM

    # Every city mention we saw was in an HQ/office context - job location is
    # genuinely unstated, not "the same as the HQ".
    return None, Confidence.NONE


def extract_work_mode(text: str, remote_terms: list[str]) -> WorkMode:
    """Remote (config-driven terms) beats hybrid beats onsite beats unknown."""
    if not text:
        return WorkMode.UNKNOWN

    lowered = text.lower()
    for term in remote_terms:
        if term.lower() in lowered:
            return WorkMode.REMOTE

    if _HYBRID_RE.search(text):
        return WorkMode.HYBRID

    if _ONSITE_RE.search(text):
        return WorkMode.ONSITE

    return WorkMode.UNKNOWN
