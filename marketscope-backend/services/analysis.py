"""The full site analysis behind POST /analyze.

    market    = weighted average of competition, road, anchor and building (each 0-25)
    potential = 4 * (w_hazard * hazard + w_market * market)                 (0-100)
    viability = potential, or 0 when zoning doesn't allow the business here

Zoning is a hard constraint and not a weighted factor. Otherwise every allowed site
would start with the same free points, and a banned one could still look viable.
docs/ENGINE_METHODOLOGY.md has the sources and reasoning.
"""
import psycopg2
from psycopg2.extras import Json

from constants.engine import (
    AHP_CRITERIA_LABELS,
    ENGINE_VERSION,
    FACTOR_MAX,
    FALLBACK_CRITERIA_WEIGHTS,
    POTENTIAL_SCALE,
)
from constants.map_layers import ZONING_ALLOWED_SCORE, ZONING_CLASSES
from constants.msme import SME_DATABASE
from core.database import DB_CONFIG
from db.schema import get_analysis_history_pk_column
from models.requests import AnalysisRequest
from services import hazard as hazard_service
from services import zoning as zoning_service
from services.ahp_weights import get_ahp_weights
from services.hazard import evaluate_hazard
from services.scoring import _get_analysis_profile, evaluate_layered_market_context
from services.verdict import classify_site
from services.zoning import evaluate_zoning
from utils.values import normalize_osm_value


# The market factors in reports: (report key, weight key, label).
MARKET_FACTORS = (
    ("competition_density", "competition", "Competition"),
    ("road_access", "road", "Road access"),
    ("anchor_proximity", "anchor", "Nearby anchors"),
    ("building_density", "building", "Building density"),
)


def zoning_state_for(zoning_score, zoning_class):
    """A site inside a mapped zone is permitted or not. With no zone to check against
    it is unverified: not a ban, and the report tells the user to confirm it."""
    if not zoning_class:
        return "unverified"
    return "permitted" if zoning_score > 0 else "not_permitted"


def combine_criteria(hazard_raw, market_raw, w_hazard, w_market):
    """(raw 0-100 potential or None, hazard weight used, market weight used).
    A missing criterion is left out and the other takes its share."""
    if hazard_raw is None and market_raw is None:
        return None, 0.0, 0.0
    if hazard_raw is None:
        return market_raw * POTENTIAL_SCALE, 0.0, 1.0
    if market_raw is None:
        return hazard_raw * POTENTIAL_SCALE, 1.0, 0.0
    total = w_hazard + w_market
    used_hazard, used_market = w_hazard / total, w_market / total
    return (hazard_raw * used_hazard + market_raw * used_market) * POTENTIAL_SCALE, used_hazard, used_market


def build_score_explanation(hazard, market_factors, used_hazard, used_market, market_weights_used):
    """One row per factor: its score, its share of the total, and the points it adds.
    The points of the available factors add up to the market potential score."""
    rows = [{
        "key": "hazard",
        "label": "Flood hazard",
        "available": hazard["raw_score"] is not None,
        "score": hazard["score"],
        "weight": round(used_hazard, 4),
        "points": round((hazard["raw_score"] or 0.0) * used_hazard * POTENTIAL_SCALE, 2),
        "max_points": round(used_hazard * FACTOR_MAX * POTENTIAL_SCALE, 2),
        "status": hazard["status"],
        "evidence": hazard["evidence"],
    }]
    for report_key, weight_key, label in MARKET_FACTORS:
        factor = market_factors[report_key]
        weight = used_market * market_weights_used.get(weight_key, 0.0)
        # Competition counts for what it is credited after the demand check.
        counted_raw = factor.get("credited_raw_score", factor["raw_score"])
        rows.append({
            "key": report_key,
            "label": label,
            "available": factor["available"],
            "score": factor.get("credited_score", factor["score"]),
            "weight": round(weight, 4),
            "points": round((counted_raw or 0.0) * weight * POTENTIAL_SCALE, 2),
            "max_points": round(weight * FACTOR_MAX * POTENTIAL_SCALE, 2),
            "status": factor["status"],
            "evidence": factor["evidence"],
        })
    return rows


def build_data_quality(missing_labels, zoning_state, warnings, weights_provenance):
    problems = len(missing_labels) + (1 if zoning_state == "unverified" else 0) + len(warnings)
    if not missing_labels and problems == 0:
        confidence = "high"
    elif len(missing_labels) <= 1 and problems <= 2:
        confidence = "medium"
    else:
        confidence = "low"

    notes = list(warnings)
    for label in missing_labels:
        notes.append(f"{label} data wasn't available, so it was left out and the other factors were re-weighted.")
    if zoning_state == "unverified":
        notes.append("This spot couldn't be checked against the zoning map. Confirm with the City Planning and Development Office.")

    return {
        "confidence": confidence,
        "missing_factors": missing_labels,
        "notes": notes,
        "weights_provenance": weights_provenance,
    }


def build_insight(verdict, potential_score, business_name, zoning_problem, explanation):
    """The plain-language recommendation, written from the same rows the report shows."""
    if verdict["key"] == "not_permitted":
        return (
            f"Not Permitted. {zoning_problem}. Securing BPLO permits here is highly unlikely, so look at another "
            f"site. If it were allowed, its market potential would be {potential_score}/100."
        )
    if verdict["key"] == "insufficient_data":
        return "Not Enough Data. The map data needed to score this site couldn't be loaded. Try scanning again shortly."

    # Market factors only: "strongest: flood hazard" would only mean the site doesn't flood.
    scored = [row for row in explanation if row["available"] and row["max_points"] > 0 and row["key"] != "hazard"]
    ranked = sorted(scored, key=lambda row: row["points"] / row["max_points"], reverse=True)
    summary = f"{verdict['label']} ({potential_score}/100) for {business_name}."
    if ranked:
        summary += f" Strongest factor: {ranked[0]['label'].lower()}."
    if len(ranked) > 1:
        summary += f" Weakest factor: {ranked[-1]['label'].lower()}."
    if verdict.get("reason"):
        summary += f" {verdict['reason']}"
    return summary


def perform_analysis(data: AnalysisRequest):
    business_key = normalize_osm_value(data.business_type) or ''
    sme_profile = SME_DATABASE.get(business_key, {"key": business_key or "shop", "val": "convenience", "fear": 5, "need": 5, "name": "MSME"})
    analysis_profile = _get_analysis_profile(business_key)
    display_name = analysis_profile.get('display_name')

    context = evaluate_layered_market_context(data.lat, data.lon, data.radius, business_key)
    competitors_list = context["competitors"]
    competitors_found = len(competitors_list)

    # ---- zoning: a constraint, not a score ------------------------------------
    zoning_score, zoning_status, zoning_class = evaluate_zoning(data.lat, data.lon, business_key)
    zoning_state = zoning_state_for(zoning_score, zoning_class)
    zoning_source = zoning_service.ZONING_LAYER_SOURCE
    zone_label = ZONING_CLASSES[zoning_class]["label"] if zoning_class else None

    if zoning_state == "not_permitted":
        zoning_problem = f"{sme_profile['name']} are not allowed in the {zone_label} under the city zoning map"
    else:
        zoning_problem = None

    if zoning_state == "unverified":
        zoning_details = (
            "This location couldn't be checked: no zoning map layer is active."
            if not zoning_source
            else f"This location is outside every zone on the active zoning layer ({zoning_source})."
        ) + " It isn't treated as banned, but confirm the zoning with the City Planning and Development Office."
    else:
        zoning_details = (
            f"Zoning comes from the active layer ({zoning_source}), based on the Panabo City Integrated Zoning Map "
            f"C.Y. 2020-2029. Matched zone: {zone_label}. Zoning is a yes-or-no check: a business that isn't allowed "
            "here gets a score of 0, whatever its market potential."
        )

    # ---- hazard ---------------------------------------------------------------
    hazard_score, hazard_status, hazard_matches = evaluate_hazard(data.lat, data.lon)
    hazard_source = hazard_service.HAZARD_LAYER_SOURCE
    hazard_available = bool(hazard_service.HAZARD_LAYER_CACHE)
    if hazard_available:
        match_text = f"Matched zone: {hazard_matches[0]}." if hazard_matches else "No mapped flood zone matched."
        hazard = {
            "raw_score": float(hazard_score),
            "score": hazard_score,
            "status": hazard_status,
            "description": f"Hazard evaluation uses the active flood hazard map layer ({hazard_source}). {match_text}",
            "details": (
                f"The hazard score comes from the flood hazard polygons of the active map layer ({hazard_source}), "
                f"clipped to Panabo. {match_text} Each point maps to at most one flood class."
            ),
            "evidence": match_text,
        }
    else:
        hazard = {
            "raw_score": None,
            "score": None,
            "status": "Hazard Data Unavailable",
            "description": "No flood hazard map layer is active, so flood risk wasn't checked for this scan.",
            "details": "No flood hazard map layer is active, so flood risk was left out of this score. This doesn't mean the site is safe.",
            "evidence": "Data not available for this scan.",
        }

    # ---- weights and total ----------------------------------------------------
    ahp_criteria = get_ahp_weights("criteria", None)
    if ahp_criteria:
        w_hazard, w_market = ahp_criteria["priority_vector"]
    else:
        w_hazard, w_market = FALLBACK_CRITERIA_WEIGHTS

    saturation = context["saturation"]
    potential_raw, used_hazard, used_market = combine_criteria(hazard["raw_score"], saturation["raw_score"], w_hazard, w_market)
    potential_score = round(potential_raw) if potential_raw is not None else 0
    total_score = 0 if zoning_state == "not_permitted" else potential_score

    verdict = classify_site(
        potential_score,
        zoning_state,
        hazard_score=hazard["score"],
        has_data=potential_raw is not None,
    )

    explanation = build_score_explanation(hazard, context, used_hazard, used_market, context["market_weights_used"])

    missing_labels = [row["label"] for row in explanation if not row["available"]]
    provenance = (ahp_criteria or {}).get("updated_by_admin_email") or "static-fallback"
    data_quality = build_data_quality(missing_labels, zoning_state, context["warnings"], provenance)
    generated_insight = build_insight(verdict, potential_score, sme_profile["name"], zoning_problem, explanation)

    ahp_methodology_payload = {
        "criteria": {
            "source": "ahp" if ahp_criteria else "static_fallback",
            "provenance": provenance,
            "criteria_labels": AHP_CRITERIA_LABELS,
            "pairwise_matrix": (ahp_criteria or {}).get("pairwise_matrix"),
            "priority_vector": [w_hazard, w_market],
            "lambda_max": (ahp_criteria or {}).get("lambda_max"),
            "consistency_index": (ahp_criteria or {}).get("ci"),
            "random_index": (ahp_criteria or {}).get("ri"),
            "consistency_ratio": (ahp_criteria or {}).get("cr"),
            "is_consistent": (ahp_criteria or {}).get("is_consistent"),
        },
        "saturation_sub_criteria": context.get("ahp_sub_criteria_methodology"),
    }

    def report_factor(factor, description, **extra):
        return {
            "available": factor["available"],
            "score": factor["score"],
            "status": factor["status"],
            "description": description,
            "details": factor["details"],
            "evidence": factor["evidence"],
            **extra,
        }

    breakdown_payload = {
        "zoning": {
            "available": zoning_state != "unverified",
            "constraint": True,
            "state": zoning_state,
            "score": ZONING_ALLOWED_SCORE if zoning_state == "permitted" else (0 if zoning_state == "not_permitted" else None),
            "status": zoning_status,
            "description": "Alignment with Panabo City Land Use Plan.",
            "details": zoning_details,
        },
        "hazard": {
            "available": hazard_available,
            "score": hazard["score"],
            "status": hazard["status"],
            "description": hazard["description"],
            "details": hazard["details"],
            "evidence": hazard["evidence"],
        },
        "competition_density": report_factor(
            context["competition_density"],
            f"Competition pressure for {display_name}",
            credited_score=context["competition_density"].get("credited_score"),
            demand_share=context["competition_density"].get("demand_share"),
            competitor_count=context["competition_density"].get("competitor_count"),
        ),
        "road_access": report_factor(
            context["road_access"],
            f"Major road and site road access for {display_name}",
            major_road=context["road_access"].get("major_road"),
        ),
        "anchor_proximity": report_factor(
            context["anchor_proximity"],
            f"Traffic generators near the site for {display_name}",
            nearby_anchors=context["anchor_proximity"].get("nearby_anchors"),
        ),
        "building_density": report_factor(
            context["building_density"],
            f"Built-up intensity around the site for {display_name}",
        ),
        "saturation": report_factor(
            saturation,
            saturation["description"],
        ),
    }

    result_meta = {
        "engine_version": ENGINE_VERSION,
        "verdict": verdict,
        "market_potential_score": potential_score,
        "score_explanation": explanation,
        "data_quality": data_quality,
    }

    if data.user_id is not None:
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()

            updated_existing = False
            if data.history_id is not None:
                # Re-scan of an already-saved report (e.g. opened from History) should
                # refresh that row in place instead of inserting a duplicate.
                history_pk_column = get_analysis_history_pk_column(cursor)
                cursor.execute(
                    f"""
                    UPDATE analysis_history
                    SET business_type = %s,
                        viability_score = %s,
                        target_lat = %s,
                        target_lon = %s,
                        radius_used = %s,
                        insight = %s,
                        competitors_found = %s,
                        competitor_locations = %s,
                        breakdown = %s,
                        ahp_methodology = %s,
                        result_meta = %s
                    WHERE user_id = %s AND {history_pk_column} = %s
                    """,
                    (
                        business_key,
                        int(total_score),
                        data.lat,
                        data.lon,
                        data.radius,
                        generated_insight,
                        competitors_found,
                        Json(competitors_list),
                        Json(breakdown_payload),
                        Json(ahp_methodology_payload),
                        Json(result_meta),
                        data.user_id,
                        data.history_id,
                    )
                )
                updated_existing = cursor.rowcount > 0

            if not updated_existing:
                # Fresh scan (or the referenced saved record no longer exists) - insert a new row.
                cursor.execute(
                    """
                    INSERT INTO analysis_history (
                        user_id, business_type, viability_score,
                        target_lat, target_lon, radius_used, insight,
                        competitors_found, competitor_locations, breakdown, ahp_methodology, result_meta
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        data.user_id,
                        business_key,
                        int(total_score),
                        data.lat,
                        data.lon,
                        data.radius,
                        generated_insight,
                        competitors_found,
                        Json(competitors_list),
                        Json(breakdown_payload),
                        Json(ahp_methodology_payload),
                        Json(result_meta),
                    )
                )

            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"History Save Error: {e}")

    return {
        "viability_score": int(total_score),
        "business_type": business_key,
        "business_label": sme_profile["name"],
        "competitors_found": competitors_found,
        "competitor_locations": competitors_list,
        "target_coords": {"lat": data.lat, "lng": data.lon},
        "radius_meters": data.radius,
        "insight": generated_insight,
        "breakdown": breakdown_payload,
        "ahp_methodology": ahp_methodology_payload,
        **result_meta,
    }
