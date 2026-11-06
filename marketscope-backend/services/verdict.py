"""The one place a score becomes words. Every page and report uses this, so one
site can't be called different things in different places.
"""
from constants.engine import (
    HAZARD_VERY_HIGH_SCORE,
    VERDICT_HIGH_MIN,
    VERDICT_MODERATE_MIN,
    VERDICTS,
)


def score_band(score) -> str:
    """"high", "moderate" or "low" for a 0-100 score."""
    value = float(score or 0)
    if value >= VERDICT_HIGH_MIN:
        return "high"
    if value >= VERDICT_MODERATE_MIN:
        return "moderate"
    return "low"


def _verdict(key, reason=None):
    return {"key": key, **VERDICTS[key], "reason": reason}


def classify_site(potential_score, zoning_state, hazard_score=None, has_data=True):
    """The verdict for a scanned site.

    zoning_state: "permitted", "not_permitted" or "unverified".
    hazard_score: the 0-25 hazard factor, or None when no hazard layer was available.
    """
    if zoning_state == "not_permitted":
        return _verdict("not_permitted", "City zoning doesn't allow this business at this location.")
    if not has_data:
        return _verdict("insufficient_data", "The map data needed to score this site couldn't be loaded.")

    band = score_band(potential_score)
    if band == "high":
        if hazard_score is not None and hazard_score <= HAZARD_VERY_HIGH_SCORE:
            return _verdict("moderately_suitable", "The market looks strong, but very high flood hazard keeps it out of the top class.")
        if zoning_state == "unverified":
            return _verdict("moderately_suitable", "The market looks strong, but zoning couldn't be confirmed here, which keeps it out of the top class.")
        return _verdict("highly_suitable")
    if band == "moderate":
        return _verdict("moderately_suitable")
    return _verdict("low_suitability")
