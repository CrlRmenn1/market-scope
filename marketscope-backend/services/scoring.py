"""Location scoring: competition, road access, anchors, building density."""
import math

import psycopg2
from psycopg2.extras import RealDictCursor

from constants.geo import PANABO_ANCHORS
from constants.msme import (
    DEFAULT_MSME_ANALYSIS_PROFILE,
    MSME_CATEGORY_PROFILES,
    ROAD_CLASS_BASE_SCORES,
    SME_DATABASE,
)
from core.database import DB_CONFIG
from db.queries import fetch_custom_msmes, fetch_verified_local_features
from db.schema import ensure_verified_local_features_table
from services import osm_data
from services.ahp_weights import get_ahp_weights
from services.osm_data import get_cached_pbf_competitors, get_name_keyword_pbf_competitors
from utils.geo import _approx_polygon_area_m2, calculate_distance
from utils.geo_libs import Point, box, nearest_points
from utils.values import _clamp_score, normalize_osm_value, to_finite_number


def _source_confidence_multiplier(source_name, confidence_score=None):
    normalized_source = normalize_osm_value(source_name)
    if normalized_source in {"verified_local", "verified", "manual_verified"}:
        base = 1.55
    elif normalized_source in {"custom_msme", "manual", "admin"}:
        base = 1.30
    else:
        base = 1.0

    confidence_value = to_finite_number(confidence_score)
    if confidence_value is None:
        return base

    confidence_scale = 0.75 + (max(0.0, min(100.0, confidence_value)) / 100.0) * 0.5
    return base * confidence_scale


def _get_analysis_profile(business_type: str | None):
    profile_key = normalize_osm_value(business_type)
    if not profile_key:
        return DEFAULT_MSME_ANALYSIS_PROFILE
    return MSME_CATEGORY_PROFILES.get(profile_key, DEFAULT_MSME_ANALYSIS_PROFILE)


def _query_context_candidates(gdf, lat, lon, radius_meters, fallback_multiplier=1.35):
    if gdf is None or Point is None or box is None:
        return None

    search_radius = max(150.0, float(radius_meters) * float(fallback_multiplier))
    lon_delta = search_radius / max(1.0, 111320.0 * max(0.2, math.cos(math.radians(lat))))
    lat_delta = search_radius / 111132.0
    search_box = box(lon - lon_delta, lat - lat_delta, lon + lon_delta, lat + lat_delta)

    if getattr(gdf, "sindex", None) is not None:
        try:
            candidate_index = list(gdf.sindex.intersection(search_box.bounds))
            if candidate_index:
                return gdf.iloc[candidate_index]
        except Exception:
            pass

    return gdf


def _score_competitor_density(lat, lon, competitors, radius_meters, profile):
    weighted_pressure = 0.0
    nearby_competitors = []
    decay_scale = max(1.0, float(radius_meters) * 0.42)

    for competitor in competitors:
        competitor_lat = to_finite_number(competitor.get("lat"))
        competitor_lon = to_finite_number(competitor.get("lon"))
        if competitor_lat is None or competitor_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, competitor_lat, competitor_lon)
        if distance_m > radius_meters:
            continue

        distance_decay = 1.0 / (1.0 + (distance_m / decay_scale))
        radial_band = 1.0 if distance_m <= radius_meters * 0.33 else 0.72 if distance_m <= radius_meters * 0.66 else 0.48
        source_name = str(competitor.get("name") or "").strip()
        source_weight = 1.15 if source_name else 1.0
        source_weight *= _source_confidence_multiplier(competitor.get("source"), competitor.get("confidence_score"))

        weighted_pressure += distance_decay * radial_band * source_weight
        nearby_competitors.append({
            "lat": competitor_lat,
            "lon": competitor_lon,
            "name": source_name or None,
            "distance_m": round(distance_m, 2),
            "source": competitor.get("source") or "osm",
        })

    competition_intensity = math.log1p(weighted_pressure * float(profile.get("competition_sensitivity") or 1.0))
    score = _clamp_score(25 - (competition_intensity * 7.0), 0, 25)

    if score >= 20:
        status = "Light Competition"
    elif score >= 15:
        status = "Manageable Competition"
    elif score >= 10:
        status = "Noticeable Competition"
    elif score >= 5:
        status = "Heavy Competition"
    else:
        status = "Highly Saturated"

    details = (
        f"Weighted competitor pressure within {radius_meters} meters is {weighted_pressure:.2f}. "
        f"The engine dampens distant points with radial decay and multi-band weighting before converting the pressure to a 0-25 inverse-density score."
    )

    return {
        "score": round(score),
        "status": status,
        "details": details,
        "weighted_pressure": round(weighted_pressure, 3),
        "competitor_count": len(nearby_competitors),
        "nearby_competitors": nearby_competitors,
    }


def _score_road_access(lat, lon, radius_meters, profile, verified_roads=None):
    verified_roads = verified_roads or []

    best_verified = None
    soft_cap = float(profile.get("road_distance_soft_cap_m") or 850.0)
    preferred_classes = set(profile.get("preferred_road_classes") or [])
    required_classes = set(profile.get("required_road_classes") or [])

    for road in verified_roads:
        road_lat = to_finite_number(road.get("latitude"))
        road_lon = to_finite_number(road.get("longitude"))
        if road_lat is None or road_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, road_lat, road_lon)
        if distance_m > radius_meters:
            continue

        road_class = normalize_osm_value(road.get("road_class") or road.get("feature_subtype"))
        road_name = str(road.get("name") or "").strip() or None
        road_base_score = float(ROAD_CLASS_BASE_SCORES.get(road_class or "", 10))
        distance_factor = max(0.34, 1.0 - (distance_m / max(1.0, soft_cap)))
        score = road_base_score * distance_factor * _source_confidence_multiplier("verified_local", road.get("confidence_score"))

        if road_class in preferred_classes:
            score += 2.5
        elif road_class in required_classes:
            score += 1.0
        else:
            score -= 2.0

        if distance_m <= 120:
            score += 1.5
        elif distance_m <= 300:
            score += 0.75
        elif distance_m > soft_cap:
            score -= 1.5

        score = round(_clamp_score(score, 0, 25))

        if best_verified is None or score > best_verified["score"] or (score == best_verified["score"] and distance_m < best_verified["distance_m"]):
            best_verified = {
                "score": score,
                "road_class": road_class,
                "road_name": road_name,
                "distance_m": distance_m,
            }

    if best_verified is not None:
        if best_verified["score"] >= 20:
            status = "Excellent Road Access"
        elif best_verified["score"] >= 15:
            status = "Good Road Access"
        elif best_verified["score"] >= 10:
            status = "Moderate Road Access"
        elif best_verified["score"] >= 5:
            status = "Limited Road Access"
        else:
            status = "Poor Road Access"

        road_label = best_verified["road_class"] or "verified local road"
        details = (
            f"A manually verified road record was found approximately {best_verified['distance_m']:.1f} meters away. "
            f"Its class is {road_label}, and the score uses the verified local source hierarchy before falling back to OSM geometry."
        )

        return {
            "score": best_verified["score"],
            "status": status,
            "details": details,
            "road_class": best_verified["road_class"],
            "road_name": best_verified["road_name"],
            "distance_m": round(best_verified["distance_m"], 2),
        }

    if osm_data.PBF_ROAD_CONTEXT_GDF is None or Point is None:
        return {
            "score": 12,
            "status": "Road Context Unavailable",
            "details": "Road geometry context could not be loaded, so the engine used a neutral accessibility fallback.",
            "road_class": None,
            "road_name": None,
            "distance_m": None,
        }

    candidates = _query_context_candidates(osm_data.PBF_ROAD_CONTEXT_GDF, lat, lon, radius_meters, fallback_multiplier=1.8)
    if candidates is None or candidates.empty:
        return {
            "score": 12,
            "status": "Road Context Unavailable",
            "details": "No road candidates were found in the scan window, so the engine used a neutral accessibility fallback.",
            "road_class": None,
            "road_name": None,
            "distance_m": None,
        }

    origin = Point(lon, lat)
    best_candidate = None
    best_distance = None

    for _, row in candidates.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            continue

        try:
            nearest_point = nearest_points(origin, geometry)[1] if nearest_points is not None else geometry.representative_point()
            distance_m = calculate_distance(lat, lon, nearest_point.y, nearest_point.x)
        except Exception:
            continue

        if best_distance is None or distance_m < best_distance:
            best_distance = distance_m
            best_candidate = row

    if best_candidate is None or best_distance is None:
        return {
            "score": 12,
            "status": "Road Context Unavailable",
            "details": "The scan could not determine a stable nearest road geometry, so the engine used a neutral accessibility fallback.",
            "road_class": None,
            "road_name": None,
            "distance_m": None,
        }

    road_class = normalize_osm_value(best_candidate.get("road_class"))
    road_name = str(best_candidate.get("name") or "").strip() or None
    road_base_score_value = None
    try:
        road_base_score_value = best_candidate["road_base_score"]
    except Exception:
        road_base_score_value = None
    road_base_score = float(road_base_score_value or ROAD_CLASS_BASE_SCORES.get(road_class or "", 10))
    distance_factor = max(0.34, 1.0 - (best_distance / max(1.0, soft_cap)))

    score = road_base_score * distance_factor
    preferred_classes = set(profile.get("preferred_road_classes") or [])
    required_classes = set(profile.get("required_road_classes") or [])

    if road_class in preferred_classes:
        score += 2.5
    elif road_class in required_classes:
        score += 1.0
    else:
        score -= 2.5

    if best_distance <= 120:
        score += 1.5
    elif best_distance <= 300:
        score += 0.75
    elif best_distance > soft_cap:
        score -= 1.5

    score = round(_clamp_score(score, 0, 25))

    if score >= 20:
        status = "Excellent Road Access"
    elif score >= 15:
        status = "Good Road Access"
    elif score >= 10:
        status = "Moderate Road Access"
    elif score >= 5:
        status = "Limited Road Access"
    else:
        status = "Poor Road Access"

    road_label = road_class or "unknown"
    details = (
        f"The nearest road is {road_name or 'an unnamed road'} classified as {road_label}. "
        f"It is approximately {best_distance:.1f} meters away, and the accessibility score is dampened by distance plus category road preference rules."
    )

    return {
        "score": score,
        "status": status,
        "details": details,
        "road_class": road_class,
        "road_name": road_name,
        "distance_m": round(best_distance, 2),
    }


def _score_anchor_proximity(lat, lon, radius_meters, profile, verified_anchors=None):
    weighted_anchor_power = 0.0
    nearby_anchors = []
    scale = max(1.0, float(profile.get("anchor_scale_m") or 320.0))

    anchor_sources = list(verified_anchors or []) + list(PANABO_ANCHORS)

    for anchor in anchor_sources:
        anchor_lat = to_finite_number(anchor.get("lat"))
        anchor_lon = to_finite_number(anchor.get("lon"))
        if anchor_lat is None or anchor_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, anchor_lat, anchor_lon)
        if distance_m > radius_meters:
            continue

        power = float(anchor.get("power") or 0.0)
        distance_decay = 1.0 / (1.0 + (distance_m / scale))
        weighted_anchor_power += power * distance_decay * _source_confidence_multiplier(anchor.get("source"), anchor.get("confidence_score"))
        nearby_anchors.append({
            "name": anchor.get("name"),
            "distance_m": round(distance_m, 2),
            "power": power,
            "source": anchor.get("source") or "osm",
        })

    target_power = float(profile.get("anchor_target_power") or 36.0)
    demand_ratio = (weighted_anchor_power / max(1.0, target_power)) * 25.0
    score = round(_clamp_score(demand_ratio, 0, 25))

    if score >= 20:
        status = "Strong Traffic Generators"
    elif score >= 15:
        status = "Moderate Traffic Generators"
    elif score >= 10:
        status = "Mixed Traffic Support"
    elif score >= 5:
        status = "Weak Traffic Support"
    else:
        status = "Low Visibility"

    details = (
        f"The engine sums nearby anchor power using inverse-distance decay and normalizes the result against a category target of {target_power:.1f}. "
        f"Weighted anchor power inside the radius is {weighted_anchor_power:.2f}."
    )

    return {
        "score": score,
        "status": status,
        "details": details,
        "weighted_anchor_power": round(weighted_anchor_power, 3),
        "anchors_found": [item.get("name") for item in nearby_anchors if item.get("name")],
        "nearby_anchors": nearby_anchors,
    }


def _score_building_density(lat, lon, radius_meters, profile, verified_buildings=None):
    weighted_intensity = 0.0
    matched_features = []
    scale = max(1.0, float(profile.get("building_radius_scale_m") or radius_meters or 420.0))

    for building in verified_buildings or []:
        building_lat = to_finite_number(building.get("latitude"))
        building_lon = to_finite_number(building.get("longitude"))
        if building_lat is None or building_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, building_lat, building_lon)
        if distance_m > radius_meters:
            continue

        distance_decay = 1.0 / (1.0 + (distance_m / scale))
        feature_weight = float(building.get("feature_weight") or 1.0)
        area_m2 = to_finite_number(building.get("area_m2")) or 0.0
        area_bonus = 1.0 + min(2.0, area_m2 / 2500.0) * 0.2
        feature_weight *= _source_confidence_multiplier("verified_local", building.get("confidence_score"))

        weighted_intensity += feature_weight * distance_decay * area_bonus
        matched_features.append({
            "name": building.get("name"),
            "distance_m": round(distance_m, 2),
            "feature_weight": round(feature_weight, 2),
            "area_m2": round(area_m2, 2),
            "source": building.get("source") or "verified_local",
        })

    if osm_data.PBF_BUILDING_CONTEXT_GDF is not None and Point is not None:
        candidates = _query_context_candidates(osm_data.PBF_BUILDING_CONTEXT_GDF, lat, lon, radius_meters, fallback_multiplier=1.55)
    else:
        candidates = None

    if candidates is None or candidates.empty:
        if not matched_features:
            return {
                "score": 12,
                "status": "Building Context Unavailable",
                "details": "Building footprint context could not be loaded, so the engine used a neutral built-form fallback.",
                "weighted_intensity": 0.0,
                "matched_features": [],
            }
    else:
        for _, row in candidates.iterrows():
            geometry = row.geometry
            if geometry is None or geometry.is_empty:
                continue

            try:
                feature_point = geometry.representative_point() if hasattr(geometry, "representative_point") else geometry.centroid
                distance_m = calculate_distance(lat, lon, feature_point.y, feature_point.x)
            except Exception:
                continue

            if distance_m > radius_meters:
                continue

            distance_decay = 1.0 / (1.0 + (distance_m / scale))
            feature_weight = float(row.get("feature_weight") or 1.0)
            area_m2 = _approx_polygon_area_m2(geometry)
            area_bonus = 1.0 + min(2.0, area_m2 / 2500.0) * 0.18

            weighted_intensity += feature_weight * distance_decay * area_bonus
            matched_features.append({
                "name": row.get("name"),
                "distance_m": round(distance_m, 2),
                "feature_weight": round(feature_weight, 2),
                "area_m2": round(area_m2, 2),
                "source": "osm",
            })

    density_score = math.log1p(weighted_intensity * float(profile.get("building_weight") or 0.15)) * 8.5
    score = round(_clamp_score(density_score, 0, 25))

    if score >= 20:
        status = "Dense Built Environment"
    elif score >= 15:
        status = "Moderately Built-Up"
    elif score >= 10:
        status = "Balanced Built Form"
    elif score >= 5:
        status = "Sparse Built Form"
    else:
        status = "Very Sparse Built Form"

    details = (
        f"The engine measures built-form intensity from nearby building footprints, land-use polygons, and amenity clusters within {radius_meters} meters. "
        f"Weighted built intensity is {weighted_intensity:.2f}, then converted to a 0-25 density proxy.")

    return {
        "score": score,
        "status": status,
        "details": details,
        "weighted_intensity": round(weighted_intensity, 3),
        "matched_features": matched_features,
    }


def evaluate_layered_market_context(lat, lon, radius_meters, business_type):
    profile_key = normalize_osm_value(business_type)
    profile_key_safe = profile_key or ""
    profile = MSME_CATEGORY_PROFILES.get(profile_key_safe, DEFAULT_MSME_ANALYSIS_PROFILE)
    osm_tags = profile.get("osm_tags") or SME_DATABASE.get(profile_key_safe, {}).get("osm_tags") or [("shop", "convenience")]

    competitors_list = []
    competitor_dedupe = set()
    verified_competitors = []
    verified_roads = []
    verified_anchors = []
    verified_buildings = []

    # Share one DB connection across the several verified-feature/custom-MSME
    # lookups below instead of each one opening/closing its own (this used to
    # be up to 5 fresh connections - plus a 13-statement schema-ensure re-run
    # on every one of them - per /analyze call). If the shared connection
    # can't be opened, shared_cursor stays None and every call below falls
    # back to opening its own connection, exactly like before this change.
    shared_conn = None
    shared_cursor = None
    try:
        shared_conn = psycopg2.connect(**DB_CONFIG)
        shared_cursor = shared_conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(shared_cursor)
    except Exception as exc:
        print(f"Shared DB connection for market context failed, falling back to per-call connections: {exc}")
        shared_conn = None
        shared_cursor = None

    try:
        verified_competitors = fetch_verified_local_features("msme", business_type=business_type, cursor=shared_cursor)
        verified_roads = fetch_verified_local_features("road", cursor=shared_cursor)
        verified_anchors = fetch_verified_local_features("anchor", cursor=shared_cursor)
        verified_buildings = fetch_verified_local_features("building", cursor=shared_cursor)

        for shop in verified_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                {
                    "lat": shop.get("latitude"),
                    "lon": shop.get("longitude"),
                    "name": shop.get("name"),
                    "source": "verified_local",
                    "confidence_score": shop.get("confidence_score"),
                },
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Verified local feature scan error: {exc}")

    try:
        cached_competitors = []
        for _, tag_value in osm_tags:
            competitors = get_cached_pbf_competitors(tag_value)
            cached_competitors.extend(competitors)

        for competitor in cached_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                competitor,
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Spatial competitor scan error: {exc}")

    custom_competitors = []
    try:
        custom_competitors = fetch_custom_msmes(business_type, cursor=shared_cursor)
        for shop in custom_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                {"lat": shop.get("latitude"), "lon": shop.get("longitude"), "name": shop.get("name"), "source": "custom_msme"},
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Custom MSME competitor scan error: {exc}")
    finally:
        if shared_cursor is not None:
            shared_cursor.close()
        if shared_conn is not None:
            shared_conn.close()

    if not competitors_list:
        for competitor in get_name_keyword_pbf_competitors(business_type):
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                competitor,
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )

    competition_density = _score_competitor_density(lat, lon, competitors_list, radius_meters, profile)
    road_access = _score_road_access(lat, lon, radius_meters, profile, verified_roads=verified_roads)
    anchor_proximity = _score_anchor_proximity(lat, lon, radius_meters, profile, verified_anchors=verified_anchors)
    building_density = _score_building_density(lat, lon, radius_meters, profile, verified_buildings=verified_buildings)

    ahp_saturation = get_ahp_weights("saturation", profile_key_safe)
    if ahp_saturation:
        w_competition, w_road, w_anchor, w_building = ahp_saturation["priority_vector"]
        saturation_weight_source = "ahp"
    else:
        w_competition = float(profile.get("competition_weight") or 0.42)
        w_road = float(profile.get("road_weight") or 0.23)
        w_anchor = float(profile.get("anchor_weight") or 0.20)
        w_building = float(profile.get("building_weight") or 0.15)
        saturation_weight_source = "static_fallback"

    saturation_raw = (
        (competition_density["score"] * w_competition)
        + (road_access["score"] * w_road)
        + (anchor_proximity["score"] * w_anchor)
        + (building_density["score"] * w_building)
    )
    weight_total = w_competition + w_road + w_anchor + w_building
    saturation_score = round(_clamp_score(saturation_raw / max(0.01, weight_total), 0, 25))

    if saturation_score >= 20:
        saturation_status = "Market Gap Available"
    elif saturation_score >= 15:
        saturation_status = "Low Competition"
    elif saturation_score >= 10:
        saturation_status = "Moderate Competition"
    elif saturation_score >= 5:
        saturation_status = "High Competition"
    else:
        saturation_status = "Oversaturated"

    saturation_details = (
        f"The composite market saturation score blends competitor density, road access, traffic-generator proximity, and built-form intensity for {profile.get('display_name')}. "
        f"Weights used for this category ({saturation_weight_source}) are competition={w_competition:.2f}, road={w_road:.2f}, anchor={w_anchor:.2f}, building={w_building:.2f}. "
        f"Raw component scores are competition {competition_density['score']}, road {road_access['score']}, anchor {anchor_proximity['score']}, and building {building_density['score']}."
    )

    ahp_sub_criteria_methodology = {
        "source": saturation_weight_source,
        "criteria_labels": (ahp_saturation or {}).get("criteria_labels") or ["competition", "road", "anchor", "building"],
        "pairwise_matrix": (ahp_saturation or {}).get("pairwise_matrix"),
        "priority_vector": [w_competition, w_road, w_anchor, w_building],
        "lambda_max": (ahp_saturation or {}).get("lambda_max"),
        "consistency_index": (ahp_saturation or {}).get("ci"),
        "random_index": (ahp_saturation or {}).get("ri"),
        "consistency_ratio": (ahp_saturation or {}).get("cr"),
        "is_consistent": (ahp_saturation or {}).get("is_consistent", True),
    }

    return {
        "profile": profile,
        "competitors": competitors_list,
        "custom_competitors": custom_competitors,
        "competition_density": competition_density,
        "road_access": road_access,
        "anchor_proximity": anchor_proximity,
        "building_density": building_density,
        "ahp_sub_criteria_methodology": ahp_sub_criteria_methodology,
        "saturation": {
            "score": saturation_score,
            "status": saturation_status,
            "description": f"Composite market saturation for {profile.get('display_name')}",
            "details": saturation_details,
        },
        "component_scores": {
            "competition_density": competition_density["score"],
            "road_access": road_access["score"],
            "anchor_proximity": anchor_proximity["score"],
            "building_density": building_density["score"],
        },
    }


def collect_competitor_preview(lat, lon, radius_meters, business_type):
    profile_key = normalize_osm_value(business_type)
    profile_key_safe = profile_key or ""
    profile = MSME_CATEGORY_PROFILES.get(profile_key_safe, DEFAULT_MSME_ANALYSIS_PROFILE)
    osm_tags = profile.get("osm_tags") or SME_DATABASE.get(profile_key_safe, {}).get("osm_tags") or [("shop", "convenience")]

    competitors_list = []
    competitor_dedupe = set()

    try:
        verified_competitors = fetch_verified_local_features("msme", business_type=business_type)
        for shop in verified_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                {
                    "lat": shop.get("latitude"),
                    "lon": shop.get("longitude"),
                    "name": shop.get("name"),
                    "source": "verified_local",
                    "confidence_score": shop.get("confidence_score"),
                },
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Verified local competitor preview error: {exc}")

    try:
        cached_competitors = []
        for _, tag_value in osm_tags:
            cached_competitors.extend(get_cached_pbf_competitors(tag_value))

        for competitor in cached_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                competitor,
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Spatial competitor preview error: {exc}")

    try:
        custom_competitors = fetch_custom_msmes(business_type)
        for shop in custom_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                {"lat": shop.get("latitude"), "lon": shop.get("longitude"), "name": shop.get("name"), "source": "custom_msme"},
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Custom MSME competitor preview error: {exc}")

    if not competitors_list:
        for competitor in get_name_keyword_pbf_competitors(business_type):
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                competitor,
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )

    return {
        "business_type": profile_key_safe,
        "business_label": profile.get("display_name") or "MSME",
        "target_coords": {"lat": lat, "lng": lon},
        "radius_meters": radius_meters,
        "competitors_found": len(competitors_list),
        "competitor_locations": competitors_list,
    }


def _append_competitor_if_within_radius(competitors_list, dedupe_keys, source_item, origin_lat, origin_lon, radius_meters, default_name):
    p_lat = to_finite_number(source_item.get("lat")) if isinstance(source_item, dict) else None
    p_lon = to_finite_number(source_item.get("lon")) if isinstance(source_item, dict) else None

    if p_lat is None or p_lon is None:
        return

    distance_m = calculate_distance(origin_lat, origin_lon, p_lat, p_lon)
    if distance_m > radius_meters:
        return

    competitor_name = None
    if isinstance(source_item, dict):
        competitor_name = source_item.get("name")

    normalized_name = str(competitor_name or default_name or "").strip()
    dedupe_key = (round(p_lat, 6), round(p_lon, 6), normalized_name.lower())
    if dedupe_key in dedupe_keys:
        return

    dedupe_keys.add(dedupe_key)
    source_name = str(source_item.get("source") or "osm").strip().lower() if isinstance(source_item, dict) else "osm"
    competitors_list.append({
        "lat": p_lat,
        "lon": p_lon,
        "name": normalized_name or default_name,
        "source": source_name,
        "confidence_score": source_item.get("confidence_score") if isinstance(source_item, dict) else None
    })
