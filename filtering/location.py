"""
The core location rule for this project:

    Mumbai (or a configured alias)        -> ACCEPT, any work mode
    elsewhere + explicit remote/WFH term  -> ACCEPT
    elsewhere + hybrid/onsite/unknown     -> REJECT
    location unknown                      -> REJECT (never assume remote)
"""

from core.models import WorkMode


def location_decision(
    job_location: str | None,
    work_mode: WorkMode,
    mumbai_aliases: list[str],
) -> tuple[bool, str]:
    """Returns (location_match, reason). reason is always set, on accept or reject."""
    if job_location:
        normalized = job_location.strip().lower()
        if any(alias.lower() in normalized for alias in mumbai_aliases):
            return True, "MUMBAI_MATCH"

    # Explicit remote accepts even when we couldn't pin down a place name at
    # all (e.g. "HQ in Mumbai, hiring - Remote India" - the extractor may not
    # surface a non-HQ location string, but "remote" alone is sufficient).
    if work_mode == WorkMode.REMOTE:
        return True, "EXPLICIT_REMOTE"

    if not job_location:
        return False, "UNKNOWN_LOCATION"

    return False, f"NON_MUMBAI_NON_REMOTE:{job_location}/{work_mode.value}"
