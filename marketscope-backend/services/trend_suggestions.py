"""Business trend suggestions: which business types fit which area.

Pure functions over saved scan rows, so no database is needed to test them. All the
scores come from perform_analysis. Nothing here adds a weight or changes a score;
it only groups the results by area and orders them.

  area          - the spots nearest one named place (panabo.pbf has no barangay
                  polygons, so these are "around Gredu", not legal boundaries)
  area score    - the average of a business's best TREND_AREA_TOP_SPOTS spots there
  suggestion    - an area score in the Highly Suitable class
  competitor data "thin" - so few shops of this type are on record citywide that
                  "no competition" can't be trusted. These rank below the others
                  and are never called a market gap.

This describes current conditions. Nothing here measures change over time.
"""
from constants.engine import (
    TREND_AREA_TOP_SPOTS,
    TREND_GAP_MAX_COMPETITORS,
    TREND_GAP_MIN_DEMAND,
    TREND_MIN_KNOWN_COMPETITORS,
)
from services.verdict import classify_site
from utils.geo import calculate_distance


DATA_ADEQUATE = "adequate"
DATA_THIN = "thin"

HIGHLY_SUITABLE = "highly_suitable"


def assign_area(lat, lon, places):
    """The nearest named place, or None when there are none."""
    return min(
        places,
        key=lambda place: calculate_distance(lat, lon, place["lat"], place["lon"]),
        default=None,
    )


def competitor_data_status(known_competitors) -> str:
    return DATA_ADEQUATE if known_competitors >= TREND_MIN_KNOWN_COMPETITORS else DATA_THIN


def strongest_factor(score_explanation):
    """The market factor closest to its maximum. Same rule as the report's insight:
    flood hazard is left out, because it would only say the site doesn't flood."""
    scored = [
        row for row in score_explanation or []
        if row.get("available") and row.get("max_points") and row.get("key") != "hazard"
    ]
    if not scored:
        return None
    best = max(scored, key=lambda row: row["points"] / row["max_points"])
    return {"key": best.get("key"), "label": best.get("label"), "status": best.get("status")}


def is_market_gap(competitor_count, demand_share, data_status) -> bool:
    """Only with enough competitor data and a real count. A saved row from before
    the count was recorded has none, and "unknown" is not a gap."""
    if data_status != DATA_ADEQUATE or competitor_count is None or demand_share is None:
        return False
    return competitor_count <= TREND_GAP_MAX_COMPETITORS and demand_share >= TREND_GAP_MIN_DEMAND


def area_verdict(area_score, best_spot_verdict):
    """The verdict for a business in an area, in the same classes a single site gets.
    A flood or zoning cap on the best spot still applies. A spot scanned before
    engine 2.0 has no verdict, so None is returned and the page calls it older."""
    if not best_spot_verdict:
        return None
    verdict = classify_site(area_score, "permitted")
    if verdict["key"] == HIGHLY_SUITABLE and best_spot_verdict.get("key") != HIGHLY_SUITABLE:
        return best_spot_verdict
    return verdict


def summarize_business_in_area(business_key, business_name, rows, known_competitors, min_score):
    """One business in one area. rows are its permitted spots there (score above 0).
    Returns None when it has none, because it can't open here at all."""
    if not rows:
        return None

    ranked = sorted(rows, key=lambda row: (-row["viability_score"], row["id"]))
    top_rows = ranked[:TREND_AREA_TOP_SPOTS]
    best = top_rows[0]
    area_score = round(sum(row["viability_score"] for row in top_rows) / len(top_rows))
    verdict = area_verdict(area_score, best.get("verdict"))
    data_status = competitor_data_status(known_competitors)

    return {
        "business_key": business_key,
        "business_name": business_name,
        "score": area_score,
        "verdict": verdict,
        "is_suggestion": bool(verdict) and verdict["key"] == HIGHLY_SUITABLE and area_score >= min_score,
        "spots_checked": len(rows),
        "listed_spaces": sum(1 for row in rows if row.get("candidate_source") == "space"),
        "best_spot": {
            "result_id": best["id"],
            "lat": best["lat"],
            "lng": best["lon"],
            "label": best.get("candidate_label"),
            "source": best.get("candidate_source"),
            "score": best["viability_score"],
        },
        "strongest_factor": strongest_factor(best.get("score_explanation")),
        "competitor_count": best.get("competitor_count"),
        "known_competitors": known_competitors,
        "competitor_data": data_status,
        "market_gap": is_market_gap(best.get("competitor_count"), best.get("demand_share"), data_status),
    }


def suggestion_sort_key(entry):
    """Suggestions first, those backed by enough competitor data before the others,
    then by score. Ties go by name, so the order never shifts between page loads."""
    return (
        not entry["is_suggestion"],
        entry["competitor_data"] != DATA_ADEQUATE,
        -entry["score"],
        entry["business_name"],
    )


def rank_area_suggestions(entries):
    return sorted(entries, key=suggestion_sort_key)


def build_areas(rows_by_business, business_names, known_competitors, places, min_score):
    """Every area with at least one permitted spot, each with its businesses ranked.

    rows_by_business: {business_key: [saved row, ...]}
    """
    grouped = {}
    area_spots = {}
    for business_key, rows in rows_by_business.items():
        for row in rows:
            place = assign_area(row["lat"], row["lon"], places)
            if place is None:
                continue
            grouped.setdefault(place["name"], {}).setdefault(business_key, []).append(row)
            area_spots.setdefault(place["name"], set()).add((round(row["lat"], 4), round(row["lon"], 4)))

    areas = []
    for place in places:
        businesses = grouped.get(place["name"])
        if not businesses:
            continue
        entries = [
            summarize_business_in_area(
                business_key,
                business_names.get(business_key, business_key),
                rows,
                known_competitors.get(business_key, 0),
                min_score,
            )
            for business_key, rows in businesses.items()
        ]
        areas.append({
            "name": place["name"],
            "lat": place["lat"],
            "lng": place["lon"],
            "spots": len(area_spots[place["name"]]),
            "businesses": rank_area_suggestions(entries),
        })

    areas.sort(key=lambda area: area["name"])
    return areas


def best_areas_for_business(areas, business_key, limit):
    """The areas where one business does best, in the same order an area uses."""
    picks = []
    for area in areas:
        entry = next((item for item in area["businesses"] if item["business_key"] == business_key), None)
        if entry:
            picks.append({"area_name": area["name"], **entry})
    picks.sort(key=lambda item: (not item["is_suggestion"], -item["score"], item["area_name"]))
    return picks[:limit]
