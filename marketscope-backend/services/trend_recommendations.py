"""What the Trends page shows, read from saved background scans.

  areas    - each named area with its business types ranked (services/trend_suggestions.py)
  primary  - the user's primary business and the areas where it does best
  scan     - how far the scans of all the business types have got

Built areas are kept in memory until a business type gets a new finished run, so
polling during a scan doesn't redo the work. Preferences only add tags on top.
"""
from constants.engine import COMPETITION_REACH_M, TREND_AREA_TOP_SPOTS, TREND_MIN_KNOWN_COMPETITORS
from constants.msme import SME_DATABASE
from core.config import TREND_HIGH_CHANCE_MIN_SCORE, TREND_SCAN_FRESH_HOURS
from db.trend_queries import fetch_run_area_rows, open_trend_cursor
from services.osm_data import get_osm_place_features
from services.scoring import count_known_competitors
from services.trend_preferences import (
    describe_setup_match,
    fits_preferred_setup,
    get_all_scan_business_keys,
    resolve_primary_business_key,
)
from services.trend_scan import get_business_scan_state, request_trend_scans
from services.trend_suggestions import best_areas_for_business, build_areas


TOP_PRIMARY_AREAS = 3
ACTIVE_SCAN_STATES = ("scanning", "queued")

# (key built from the finished runs, areas). Replaced as a whole, so a reader never
# sees it half-written.
_AREAS_CACHE = (None, [])


def _load_areas(cursor, done_runs):
    """done_runs: {business_key: its newest finished run}."""
    global _AREAS_CACHE
    cache_key = tuple(sorted((business_key, run["id"]) for business_key, run in done_runs.items()))
    if _AREAS_CACHE[0] == cache_key:
        return _AREAS_CACHE[1]

    rows_by_business = {
        business_key: [{**row, "lat": float(row["lat"]), "lon": float(row["lon"])} for row in fetch_run_area_rows(cursor, run["id"])]
        for business_key, run in done_runs.items()
    }
    areas = build_areas(
        rows_by_business,
        {key: SME_DATABASE[key]["name"] for key in done_runs},
        {key: count_known_competitors(key, cursor=cursor) for key in done_runs},
        get_osm_place_features(),
        TREND_HIGH_CHANCE_MIN_SCORE,
    )
    _AREAS_CACHE = (cache_key, areas)
    return areas


def _tag_for_user(areas, user_profile):
    """A copy of the areas with this user's setup tags. The ranking isn't changed."""
    return [
        {
            **area,
            "businesses": [
                {**entry, "fits_setup": fits_preferred_setup(entry["business_key"], user_profile)}
                for entry in area["businesses"]
            ],
        }
        for area in areas
    ]


def _summarize_scans(scan_states):
    """scan_states: {business_key: get_business_scan_state(...)}."""
    active = {key: state for key, state in scan_states.items() if state["state"] in ACTIVE_SCAN_STATES}
    current = next(
        (
            {"business_name": SME_DATABASE[key]["name"], **state["progress"]}
            for key, state in active.items()
            if state["state"] == "scanning" and state["progress"]
        ),
        None,
    )
    failed = [
        {
            "business_key": key,
            "business_name": SME_DATABASE[key]["name"],
            "error": state["error"],
            "has_older_results": state["done_run"] is not None,
        }
        for key, state in scan_states.items()
        if state["error"]
    ]
    ages = [state["done_run"]["age_seconds"] for state in scan_states.values() if state["done_run"]]

    return {
        "is_active": bool(active),
        "total_types": len(scan_states),
        "finished_types": sum(1 for state in scan_states.values() if state["done_run"]),
        "current": current,
        "failed": failed,
        "oldest_seconds_ago": max(ages) if ages else None,
    }


def _build_primary(primary_key, areas, user_profile):
    if not primary_key:
        return None
    return {
        "business_key": primary_key,
        "business_name": SME_DATABASE[primary_key]["name"],
        "setup_match": describe_setup_match(primary_key, user_profile),
        "best_areas": best_areas_for_business(areas, primary_key, TOP_PRIMARY_AREAS),
    }


def build_user_trends(user_profile, trigger_source: str = "page", force: bool = False):
    primary_key = resolve_primary_business_key(user_profile)
    business_keys = get_all_scan_business_keys(user_profile)
    request_trend_scans(business_keys, trigger_source, force=force)

    with open_trend_cursor() as cursor:
        scan_states = {key: get_business_scan_state(cursor, key) for key in business_keys}
        done_runs = {key: state["done_run"] for key, state in scan_states.items() if state["done_run"]}
        areas = _tag_for_user(_load_areas(cursor, done_runs), user_profile)

    return {
        "status": "success",
        "settings": {
            "high_chance_min_score": TREND_HIGH_CHANCE_MIN_SCORE,
            "fresh_hours": TREND_SCAN_FRESH_HOURS,
            "min_known_competitors": TREND_MIN_KNOWN_COMPETITORS,
            "competition_reach_meters": int(COMPETITION_REACH_M),
            "area_top_spots": TREND_AREA_TOP_SPOTS,
        },
        "profile": {
            "primary_business": user_profile.get("primary_business"),
            "preferred_setup": user_profile.get("preferred_setup"),
        },
        "scan": _summarize_scans(scan_states),
        "areas": areas,
        "primary": _build_primary(primary_key, areas, user_profile),
    }
