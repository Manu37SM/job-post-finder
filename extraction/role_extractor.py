"""
Deterministic role extraction. Matches configured phrases with word boundaries -
no fuzzy matching, no treating every "Java" mention as a Java job.
"""

import re

from core.models import Confidence

_ROLE_WORDS = {"developer", "engineer"}


def extract_role(text: str, target_roles: list[str]) -> tuple[str | None, Confidence]:
    """
    HIGH: an exact configured role phrase (from target_roles) is present.
    MEDIUM: no configured phrase matches, but "java" and a role word
            (developer/engineer) both appear within a short token window -
            a weak signal worth keeping for review, not for auto-accept.
    NONE: nothing found.
    """
    if not text or not target_roles:
        return None, Confidence.NONE

    exact = _find_exact_role(text, target_roles)
    if exact is not None:
        return exact, Confidence.HIGH

    if _has_partial_java_role_signal(text):
        return None, Confidence.MEDIUM

    return None, Confidence.NONE


def _find_exact_role(text: str, target_roles: list[str]) -> str | None:
    lowered = text.lower()
    # Longest phrase first so "Senior Java Developer" isn't shadowed by a
    # shorter alias that also happens to be configured.
    hits: list[tuple[str, int]] = []
    for role in sorted(target_roles, key=len, reverse=True):
        pattern = r"\b" + re.escape(role.lower()) + r"\b"
        match = re.search(pattern, lowered)
        if match:
            hits.append((role, match.start()))
    if not hits:
        return None
    hits.sort(key=lambda h: h[1])  # earliest occurrence in the post wins
    return hits[0][0]


def _has_partial_java_role_signal(text: str, window: int = 4) -> bool:
    tokens = re.findall(r"[a-z]+", text.lower())
    if "java" not in tokens:
        return False
    for i, token in enumerate(tokens):
        if token in _ROLE_WORDS:
            nearby = tokens[max(0, i - window) : i + window + 1]
            if "java" in nearby:
                return True
    return False
