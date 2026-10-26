"""
Drops obvious non-hiring posts (courses, bootcamps, job-seeker posts...) before
the more expensive location/role logic runs. Deliberately simple substring
matching against a configured keyword list - see config.example.json
`exclude_keywords`.
"""


def check_exclusion(text: str, exclude_keywords: list[str]) -> tuple[bool, str | None]:
    """Returns (excluded, matched_keyword). (False, None) if nothing matched."""
    if not text or not exclude_keywords:
        return False, None

    lowered = text.lower()
    for keyword in exclude_keywords:
        if keyword.lower() in lowered:
            return True, keyword
    return False, None
