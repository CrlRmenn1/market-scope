"""What the Trends page shows, read from saved background scans.

  primary        - the user's primary business: scan state + its best spots
  setup_matches  - other business types usually run in the user's preferred
                   setup; the TOP_SETUP_MATCHES whose best spot scored highest

Spots are saved results with viability_score >= TREND_HIGH_CHANCE_MIN_SCORE,
best first (max MAX_SPOTS_PER_SECTION). If none reach the cut-off, the best
FALLBACK_SPOTS are returned marked is_high_chance=False.
Sorting by viability score is the only ranking rule, for spots and for setup matches.
"""
from constants.msme import SME_DATABASE
from core.config import TREND_HIGH_CHANCE_MIN_SCORE, TREND_SCAN_FRESH_HOURS, TREND_SCAN_RADIUS
from db.trend_queries import count_run_results, fetch_run_results, open_trend_cursor
from services.trend_preferences import (
    describe_setup_match,
    get_same_setup_business_keys,
    resolve_primary_business_key,
)
from services.trend_scan import get_business_scan_state, request_trend_scans


MAX_SPOTS_PER_SECTION = 5
FALLBACK_SPOTS = 3
TOP_SETUP_MATCHES = 2
ACTIVE_SCAN_STATES = ("scanning", "queued")


def summarize_spot(report):
    """Short highlights taken straight from the /analyze breakdown of a spot."""
    breakdown = report.get("breakdown") or {}
    highlights = []

    zoning_status = (breakdown.get("zoning") or {}).get("status")
    if zoning_status:
        highlights.append(f"Zoning: {zoning_status}")

    hazard_status = (breakdown.get("hazard") or {}).get("status")
    if hazard_status:
        highlights.append(f"Flood hazard: {hazard_status}")

    competitors_found = report.get("competitors_found")
    radius = report.get("radius_meters")
    if competitors_found is not None and radius:
        highlights.append(f"{competitors_found} competitor{'s' if competitors_found != 1 else ''} within {radius} m")

    road_status = (breakdown.get("road_access") or {}).get("status")
    if road_status:
        highlights.append(f"Road access: {road_status}")

    return highlights


def rank_setup_matches(sections, limit: int = TOP_SETUP_MATCHES):
    """Sections with saved spots, best spot score first (ties: business name)."""
    ranked = [section for section in sections if section.get("spots")]
    ranked.sort(key=lambda section: (-section["spots"][0]["viability_score"], section["business_name"]))
    return ranked[:limit]


def _build_spot(rank: int, row):
    space = row.get("space_context")
    score = int(row.get("viability_score") or 0)
    return {
        "rank": rank,
        "result_id": row["id"],
        "lat": row["lat"],
        "lng": row["lon"],
        "source": row["candidate_source"],
        "label": row.get("candidate_label"),
        "is_listed_space": row["candidate_source"] == "space" or bool(space),
        "space": space,
        "viability_score": score,
        "is_high_chance": score >= TREND_HIGH_CHANCE_MIN_SCORE,
        "insight": row.get("insight"),
        "highlights": summarize_spot(row),
    }


def _build_section(cursor, business_key: str):
    scan_state = get_business_scan_state(cursor, business_key)
    done_run = scan_state["done_run"]

    spots = []
    scanned_spots = 0
    high_chance_spots = 0
    if done_run:
        scanned_spots, high_chance_spots = count_run_results(cursor, done_run["id"], TREND_HIGH_CHANCE_MIN_SCORE)
        rows = fetch_run_results(cursor, done_run["id"], MAX_SPOTS_PER_SECTION)
        high_rows = [row for row in rows if row["viability_score"] >= TREND_HIGH_CHANCE_MIN_SCORE]
        chosen_rows = high_rows if high_rows else rows[:FALLBACK_SPOTS]
        spots = [_build_spot(index + 1, row) for index, row in enumerate(chosen_rows)]

    return {
        "business_key": business_key,
        "business_name": SME_DATABASE[business_key]["name"],
        "scan": {
            "state": scan_state["state"],
            "progress": scan_state["progress"],
            "error": scan_state["error"],
            "run_id": done_run["id"] if done_run else None,
            "scanned_seconds_ago": done_run["age_seconds"] if done_run else None,
            "scanned_spots": scanned_spots,
            "high_chance_spots": high_chance_spots,
        },
        "spots": spots,
    }


def build_user_trends(user_profile, trigger_source: str = "page", force: bool = False):
    primary_key = resolve_primary_business_key(user_profile)
    setup_keys = get_same_setup_business_keys(user_profile, exclude=primary_key)
    request_trend_scans(([primary_key] if primary_key else []) + setup_keys, trigger_source, force=force)

    with open_trend_cursor() as cursor:
        primary = None
        if primary_key:
            primary = _build_section(cursor, primary_key)
            primary["setup_match"] = describe_setup_match(primary_key, user_profile)
        setup_sections = [_build_section(cursor, business_key) for business_key in setup_keys]

    return {
        "status": "success",
        "settings": {
            "high_chance_min_score": TREND_HIGH_CHANCE_MIN_SCORE,
            "fresh_hours": TREND_SCAN_FRESH_HOURS,
            "radius_meters": TREND_SCAN_RADIUS,
        },
        "profile": {
            "primary_business": user_profile.get("primary_business"),
            "preferred_setup": user_profile.get("preferred_setup"),
        },
        "primary": primary,
        "setup_matches": {
            "setup": user_profile.get("preferred_setup"),
            "total": len(setup_sections),
            "scanned": sum(1 for section in setup_sections if section["scan"]["run_id"] is not None),
            "is_scanning": any(section["scan"]["state"] in ACTIVE_SCAN_STATES for section in setup_sections),
            "sections": rank_setup_matches(setup_sections),
        },
    }
