"""What the Trends page shows: one section per picked business type, read from saved scans.

For each business type from pick_trend_business_types():
  - the scan state (ready / scanning with progress / queued / failed ...)
  - the profile-fit checks
  - the spots: saved results with viability_score >= TREND_HIGH_CHANCE_MIN_SCORE,
    best first (max MAX_SPOTS_PER_SECTION). If none reach the cut-off, the best
    FALLBACK_SPOTS are returned marked is_high_chance=False.
Sorting by viability score is the only ranking rule.
"""
from constants.msme import SME_DATABASE
from core.config import TREND_HIGH_CHANCE_MIN_SCORE, TREND_SCAN_FRESH_HOURS, TREND_SCAN_RADIUS
from db.trend_queries import count_run_results, fetch_run_results, open_trend_cursor
from services.trend_scan import get_business_scan_state, request_trend_scans
from services.trend_scoring import evaluate_business_fit, pick_trend_business_types, summarize_spot


MAX_SPOTS_PER_SECTION = 5
FALLBACK_SPOTS = 3


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


def _build_section(cursor, pick, user_profile):
    business_key = pick["business_key"]
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
        "role": pick["role"],
        "fit": evaluate_business_fit(business_key, user_profile),
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
    picks = pick_trend_business_types(user_profile)
    request_trend_scans([pick["business_key"] for pick in picks], trigger_source, force=force)

    with open_trend_cursor() as cursor:
        sections = [_build_section(cursor, pick, user_profile) for pick in picks]

    return {
        "status": "success",
        "settings": {
            "high_chance_min_score": TREND_HIGH_CHANCE_MIN_SCORE,
            "fresh_hours": TREND_SCAN_FRESH_HOURS,
            "radius_meters": TREND_SCAN_RADIUS,
        },
        "profile": {
            "primary_business": user_profile.get("primary_business"),
            "startup_capital": user_profile.get("startup_capital"),
            "preferred_setup": user_profile.get("preferred_setup"),
            "target_payback_months": user_profile.get("target_payback_months"),
        },
        "sections": sections,
    }
