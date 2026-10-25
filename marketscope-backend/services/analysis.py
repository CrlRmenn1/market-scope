"""The full site analysis behind POST /analyze."""
import psycopg2
from psycopg2.extras import Json

from constants.msme import SME_DATABASE
from core.database import DB_CONFIG
from db.schema import get_analysis_history_pk_column
from models.requests import AnalysisRequest
from services import hazard as hazard_service
from services import zoning as zoning_service
from services.ahp_weights import get_ahp_weights
from services.hazard import evaluate_hazard
from services.scoring import _get_analysis_profile, evaluate_layered_market_context
from services.zoning import evaluate_zoning
from utils.values import normalize_osm_value


def perform_analysis(data: AnalysisRequest):
    business_key = normalize_osm_value(data.business_type) or ''
    sme_profile = SME_DATABASE.get(business_key, {"key": business_key or "shop", "val": "convenience", "fear": 5, "need": 5, "name": "MSME"})
    analysis_profile = _get_analysis_profile(business_key)
    print(
        f"[DEBUG] perform_analysis: business_type={business_key}, lat={data.lat}, lon={data.lon}, radius={data.radius}, "
        f"profile={analysis_profile.get('display_name')}, competition_weight={analysis_profile.get('competition_weight')}"
    )

    preflight_context = evaluate_layered_market_context(data.lat, data.lon, data.radius, business_key)

    # FACTOR 1: ZONING - Normalized to 0-25 scale, from the active zoning map layer
    zoning_score, zoning_status, zoning_class = evaluate_zoning(data.lat, data.lon, business_key)

    # FACTOR 2: HAZARD
    hazard_score, hazard_status, hazard_matches = evaluate_hazard(data.lat, data.lon)
    hazard_source = hazard_service.HAZARD_LAYER_SOURCE
    if hazard_service.HAZARD_LAYER_CACHE:
        hazard_description = (
            f"Hazard evaluation uses the active flood hazard map layer ({hazard_source}). "
            + ("Matched zone: " + hazard_matches[0] + "." if hazard_matches else "No mapped hazard zone matched.")
        )
    else:
        hazard_description = "No flood hazard map layer is active, so no hazard class was applied to this scan."

    competition_density = preflight_context["competition_density"]
    road_access = preflight_context["road_access"]
    anchor_proximity = preflight_context["anchor_proximity"]
    building_density = preflight_context["building_density"]
    saturation_score = preflight_context["saturation"]["score"]
    saturation_status = preflight_context["saturation"]["status"]
    saturation_details = preflight_context["saturation"]["details"]
    competitors_list = preflight_context["competitors"]
    competitors_found = len(competitors_list)

    if hazard_service.HAZARD_LAYER_CACHE:
        hazard_details = (
            f"The hazard score is based on the flood hazard polygons of the active map layer ({hazard_source}), clipped to Panabo. "
            + ("Matched zone: " + hazard_matches[0] + ". " if hazard_matches else "No mapped flood zone matched. ")
            + "Hazard classes are made mutually exclusive by priority (Very High > High > Moderate), so each point can map to at most one zone."
        )
    else:
        hazard_details = (
            "No flood hazard map layer is active (or it has no polygons), so the engine returned Low Risk / Safe "
            "instead of guessing a hazard class."
        )

    zoning_source = zoning_service.ZONING_LAYER_SOURCE
    if zoning_source:
        zoning_details = (
            f"The zoning score is derived by checking which polygon of the active zoning map layer ({zoning_source}) contains the target coordinates. "
            + "Commercial areas score 25, mixed-use 20, residential 10, institutional and agricultural 5. Industrial areas score 25 for businesses "
            + "that fit agri-industrial support and 5 for everything else. A site outside every mapped zone scores 0."
            + (f" Matched zone class: {zoning_class.replace('_', '-')}." if zoning_class else "")
        )
    else:
        zoning_details = "No zoning map layer is active, so no zoning credit was applied to this scan."

    ahp_criteria = get_ahp_weights("criteria", None)
    if ahp_criteria:
        w_zoning, w_hazard, w_saturation = ahp_criteria["priority_vector"]
        criteria_weight_source = "ahp"
    else:
        w_zoning, w_hazard, w_saturation = 0.30, 0.20, 0.50
        criteria_weight_source = "static_fallback"

    total_score = round(((zoning_score * w_zoning) + (hazard_score * w_hazard) + (saturation_score * w_saturation)) * 4)

    ahp_criteria_methodology = {
        "source": criteria_weight_source,
        "criteria_labels": (ahp_criteria or {}).get("criteria_labels") or ["zoning", "hazard", "saturation"],
        "pairwise_matrix": (ahp_criteria or {}).get("pairwise_matrix"),
        "priority_vector": [w_zoning, w_hazard, w_saturation],
        "lambda_max": (ahp_criteria or {}).get("lambda_max"),
        "consistency_index": (ahp_criteria or {}).get("ci"),
        "random_index": (ahp_criteria or {}).get("ri"),
        "consistency_ratio": (ahp_criteria or {}).get("cr"),
        "is_consistent": (ahp_criteria or {}).get("is_consistent", True),
    }
    ahp_methodology_payload = {
        "criteria": ahp_criteria_methodology,
        "saturation_sub_criteria": preflight_context.get("ahp_sub_criteria_methodology"),
    }

    # STATIC REPORTING MODULE (Combinational Matrix)
    if zoning_score <= 5:
        generated_insight = f"Critical Warning: This location is in a {zoning_status.lower()}. Even if market conditions are favorable, securing BPLO permits will be highly unlikely. Reconsider this site."
    elif hazard_score <= 5 and anchor_proximity["score"] >= 15:
        generated_insight = f"High Risk, High Reward (Score: {int(total_score)}). The location attracts strong traffic generators, but it is also exposed to severe flood risk. Any development plan must account for mitigation, insurance, and resilient design."
    elif saturation_score >= 20 and road_access["score"] >= 18 and anchor_proximity["score"] >= 18:
        generated_insight = f"Prime Market Gap (Score: {int(total_score)}). The site combines excellent road access, strong traffic generators, and a low competitive burden. This is the strongest placement profile in the current scan window."
    elif saturation_score <= 10 and competition_density["score"] <= 10:
        generated_insight = f"Competitive Hotspot (Score: {int(total_score)}). The corridor shows clustered competitors and the inverse-density score is weak, so this location will demand sharper differentiation and pricing discipline."
    elif anchor_proximity["score"] < 10 and road_access["score"] < 10:
        generated_insight = f"Low Visibility (Score: {int(total_score)}). The site lacks strong traffic generators and does not sit on a high-value road class, so footfall generation will depend heavily on destination marketing."
    elif total_score >= 70:
        generated_insight = f"Favorable Location (Score: {int(total_score)}). Strong overall metrics with manageable risks. The balance of foot traffic and market saturation provides a stable environment for this {sme_profile['name']}."
    elif total_score >= 45:
        generated_insight = f"Moderate Viability (Score: {int(total_score)}). This site has mixed indicators. Review the breakdown below—you will need to strategically compensate for environmental risks or lower market visibility."
    else:
        generated_insight = f"Not Recommended (Score: {int(total_score)}). Poor overall suitability. A combination of low demand, environmental hazards, or zoning issues makes this a highly unfavorable location."

    breakdown_payload = {
        "zoning": {
            "score": zoning_score,
            "status": zoning_status,
            "description": "Alignment with Panabo City Land Use Plan.",
            "details": zoning_details,
        },
        "hazard": {
            "score": hazard_score,
            "status": hazard_status,
            "description": hazard_description,
            "details": hazard_details,
        },
        "competition_density": {
            "score": competition_density["score"],
            "status": competition_density["status"],
            "description": f"Inverse-density competition pressure for {analysis_profile.get('display_name')}",
            "details": competition_density["details"],
        },
        "road_access": {
            "score": road_access["score"],
            "status": road_access["status"],
            "description": f"Nearest OSM road class and accessibility fit for {analysis_profile.get('display_name')}",
            "details": road_access["details"],
        },
        "anchor_proximity": {
            "score": anchor_proximity["score"],
            "status": anchor_proximity["status"],
            "description": f"Traffic-generator proximity using Panabo anchor points for {analysis_profile.get('display_name')}",
            "details": anchor_proximity["details"],
        },
        "building_density": {
            "score": building_density["score"],
            "status": building_density["status"],
            "description": f"Built-form intensity around the site for {analysis_profile.get('display_name')}",
            "details": building_density["details"],
        },
        "saturation": {
            "score": saturation_score,
            "status": saturation_status,
            "description": f"Composite market saturation score for {analysis_profile.get('display_name')}",
            "details": saturation_details,
        },
    }

    if data.user_id is not None:
        try:
            sanitized_competitors_list = competitors_list if competitors_found > 0 else []

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
                        ahp_methodology = %s
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
                        Json(sanitized_competitors_list),
                        Json(breakdown_payload),
                        Json(ahp_methodology_payload),
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
                        competitors_found, competitor_locations, breakdown, ahp_methodology
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        Json(sanitized_competitors_list),
                        Json(breakdown_payload),
                        Json(ahp_methodology_payload)
                    )
                )

            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"History Save Error: {e}")

    # FINAL PAYLOAD
    print(f"[DEBUG] Final score for {business_key} at ({data.lat},{data.lon}): {int(total_score)}\n---")
    return {
        "viability_score": int(total_score),
        "business_type": business_key,
        "business_label": sme_profile["name"],
        "competitors_found": competitors_found,
        "competitor_locations": competitors_list if competitors_found > 0 else [],
        "target_coords": {"lat": data.lat, "lng": data.lon},
        "radius_meters": data.radius,
        "insight": generated_insight,
        "breakdown": breakdown_payload,
        "ahp_methodology": ahp_methodology_payload,
    }
