"""
Combines independent signals into a relevance_score and match_reasons list -
"I want to know WHY a post was included" (spec).

Not a gate by itself: location_match and role_match (computed upstream) are
still what decide accept/reject in pipeline.py. This function only runs on
posts that already passed those, and its score is informational plus an
optional extra `minimum_relevance_score` threshold in config - it never
overrides the location/role decisions.
"""

from core.models import Confidence, ExtractedPost, WorkMode


def compute_relevance(
    extracted: ExtractedPost,
    location_match: bool,
    role_match: bool,
    hiring_signal: bool,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if role_match:
        score += 1
        if extracted.role_confidence == Confidence.HIGH and extracted.job_role:
            reasons.append(f"{extracted.job_role} detected")
        else:
            reasons.append("Partial Java role signal detected")

    if location_match:
        score += 1
        if extracted.work_mode == WorkMode.REMOTE:
            reasons.append("Remote detected")
        elif extracted.job_location:
            reasons.append(f"{extracted.job_location} detected")

    if hiring_signal:
        score += 1
        reasons.append("Hiring language detected")

    if extracted.primary_email:
        score += 1
        reasons.append("Recruitment email detected")

    if extracted.company:
        score += 1
        reasons.append(f"Company detected: {extracted.company}")

    return score, reasons
