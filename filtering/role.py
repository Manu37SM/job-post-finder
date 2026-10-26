"""
Whether a role_extractor result counts as a "role match" for filtering purposes.
Kept separate from extraction/role_extractor.py per the project's layering:
extraction detects, filtering decides.
"""

from core.models import Confidence


def role_matches(role_confidence: Confidence) -> bool:
    return role_confidence in (Confidence.HIGH, Confidence.MEDIUM)
