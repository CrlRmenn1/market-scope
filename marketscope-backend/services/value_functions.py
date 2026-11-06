"""The value functions: turn a measured distance into a 0-1 suitability value.

All of them are continuous, so moving a pin a little can only move a score a
little. The study uses 3-step classes; we interpolate between its breakpoints
instead, because a step lets a one-metre move jump a whole class.
"""
from constants.engine import (
    ANCHOR_CATEGORIES,
    ANCHOR_ZERO_FACTOR,
    BUILDING_REACH_M,
    COMPETITION_REACH_M,
    DEFAULT_ANCHOR_CATEGORY,
    ROAD_FRONTAGE_BANDS_M,
    ROAD_MAJOR_BANDS_M,
)


def band_membership(distance_m: float, full_m: float, half_m: float, zero_m: float) -> float:
    """1 up to full_m, falling to 0.5 at half_m, falling to 0 at zero_m."""
    if distance_m <= full_m:
        return 1.0
    if distance_m <= half_m:
        return 1.0 - 0.5 * (distance_m - full_m) / (half_m - full_m)
    if distance_m < zero_m:
        return 0.5 * (zero_m - distance_m) / (zero_m - half_m)
    return 0.0


def linear_fade(distance_m: float, reach_m: float) -> float:
    """1 at the site, falling evenly to 0 at reach_m."""
    return max(0.0, 1.0 - distance_m / reach_m)


def road_major_value(distance_m: float) -> float:
    return band_membership(distance_m, *ROAD_MAJOR_BANDS_M)


def road_frontage_value(distance_m: float) -> float:
    return band_membership(distance_m, *ROAD_FRONTAGE_BANDS_M)


def anchor_category(category) -> str:
    return category if category in ANCHOR_CATEGORIES else DEFAULT_ANCHOR_CATEGORY


def anchor_reach_m(category) -> float:
    _, half_m = ANCHOR_CATEGORIES[anchor_category(category)]["bands_m"]
    return half_m * ANCHOR_ZERO_FACTOR


def anchor_value(distance_m: float, category) -> float:
    full_m, half_m = ANCHOR_CATEGORIES[anchor_category(category)]["bands_m"]
    return band_membership(distance_m, full_m, half_m, half_m * ANCHOR_ZERO_FACTOR)


def competitor_pull(distance_m: float) -> float:
    return linear_fade(distance_m, COMPETITION_REACH_M)


def building_pull(distance_m: float) -> float:
    return linear_fade(distance_m, BUILDING_REACH_M)
