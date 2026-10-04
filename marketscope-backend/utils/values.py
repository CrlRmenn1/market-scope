"""Small value-normalization helpers used across scoring and data loading."""
import math


def normalize_osm_value(value):
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except Exception:
        pass

    normalized = str(value).strip().lower()
    return normalized or None


def to_finite_number(value):
    try:
        parsed = float(value)
    except Exception:
        return None

    if math.isfinite(parsed):
        return parsed
    return None


def _clamp_score(value, minimum=0, maximum=25):
    try:
        numeric = float(value)
    except Exception:
        numeric = minimum
    return max(minimum, min(maximum, numeric))
