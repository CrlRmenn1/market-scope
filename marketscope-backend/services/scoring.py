"""Location scoring: competition, road access, anchors, building density.

Each factor is scored 0-25 from fixed distances (constants/engine.py), so the same
pin and business always get the same score. The scan radius only decides which
competitors are listed on the map.

A factor whose data couldn't be loaded returns available=False and score=None. It is
left out of the total and the report says so; it never gets a stand-in score.
"""
import math

import psycopg2
from psycopg2.extras import RealDictCursor

from constants.engine import (
    AHP_MARKET_LABELS,
    ANCHOR_TARGET_SCALE,
    BUILDING_CURVE,
    BUILDING_REACH_M,
    BUILDING_SCALE,
    COMPETITION_CURVE,
    COMPETITION_REACH_M,
    COMPETITOR_DEDUPE_M,
    DEMAND_FACTORS,
    FACTOR_MAX,
    ROAD_CLASS_VALUES,
    ROAD_FRONTAGE_SHARE,
    ROAD_IGNORED_CLASSES,
    ROAD_MAJOR_CLASSES,
    ROAD_MAJOR_SHARE,
    ROAD_SEARCH_M,
)
from constants.msme import (
    DEFAULT_MSME_ANALYSIS_PROFILE,
    MSME_CATEGORY_PROFILES,
    SME_DATABASE,
)
from core.database import DB_CONFIG
from db.queries import fetch_custom_msmes, fetch_verified_local_features
from db.schema import ensure_verified_local_features_table
from services import osm_data
from services.ahp_weights import get_ahp_weights
from services.anchors import get_scoring_anchors
from services.osm_data import get_cached_pbf_competitors, get_name_keyword_pbf_competitors
from services.value_functions import (
    anchor_reach_m,
    anchor_value,
    building_pull,
    competitor_pull,
    road_frontage_value,
    road_major_value,
)
from utils.geo import calculate_distance
from utils.values import _clamp_score, normalize_osm_value, to_finite_number


def _get_analysis_profile(business_type: str | None):
    profile_key = normalize_osm_value(business_type)
    if not profile_key:
        return DEFAULT_MSME_ANALYSIS_PROFILE
    return MSME_CATEGORY_PROFILES.get(profile_key, DEFAULT_MSME_ANALYSIS_PROFILE)


def _status_for(score, labels):
    """labels: the wording for scores of at least 20, 15, 10, 5, and below that."""
    for threshold, label in zip((20, 15, 10, 5), labels):
        if score >= threshold:
            return label
    return labels[-1]


def _factor(raw_score, status, details, evidence, **extra):
    """raw_score keeps full precision for the total; score is what people read."""
    return {
        "available": True,
        "score": round(raw_score, 1),
        "raw_score": raw_score,
        "status": status,
        "details": details,
        "evidence": evidence,
        **extra,
    }


def _unavailable_factor(status, details, **extra):
    return {
        "available": False,
        "score": None,
        "raw_score": None,
        "status": status,
        "details": details,
        "evidence": "Data not available for this scan.",
        **extra,
    }


# ---- competition ----------------------------------------------------------------

def _score_competitor_density(lat, lon, competitors, profile):
    """Each competitor adds pressure, fading with distance. One shop counts as one
    shop whichever source listed it."""
    pressure = 0.0
    counted = []
    for competitor in competitors:
        distance_m = competitor.get("distance_m")
        if distance_m is None:
            distance_m = calculate_distance(lat, lon, competitor["lat"], competitor["lon"])
        pull = competitor_pull(distance_m)
        if pull <= 0.0:
            continue
        pressure += pull
        counted.append({**competitor, "distance_m": round(distance_m, 2)})

    counted.sort(key=lambda item: item["distance_m"])
    sensitivity = float(profile.get("competition_sensitivity") or 1.0)
    raw_score = _clamp_score(FACTOR_MAX - COMPETITION_CURVE * math.log1p(pressure * sensitivity), 0, FACTOR_MAX)
    status = _status_for(
        raw_score,
        ("Light Competition", "Manageable Competition", "Noticeable Competition", "Heavy Competition", "Highly Saturated"),
    )

    reach = int(COMPETITION_REACH_M)
    if counted:
        closest = counted[0]
        evidence = (
            f"{len(counted)} competitor{'s' if len(counted) != 1 else ''} within {reach} m; "
            f"closest is {closest.get('name') or 'an unnamed shop'} at {round(closest['distance_m'])} m."
        )
    else:
        evidence = f"No competitors on record within {reach} m."

    return _factor(
        raw_score,
        status,
        (
            f"Every known competitor within {reach} m adds pressure that fades evenly with distance. "
            f"Total pressure here is {pressure:.2f}, and more pressure means a lower score. "
            "Only competitors on OpenStreetMap or added by the admin can be counted. "
            "In the total, this score is scaled by nearby demand, because an empty area has no competitors but no customers either."
        ),
        evidence,
        weighted_pressure=round(pressure, 3),
        competitor_count=len(counted),
    )


# ---- road access ----------------------------------------------------------------

def _nearest_roads(lat, lon, verified_roads):
    """{road class: (distance_m, name)}: the closest road of each class, from OSM and verified records."""
    nearest = {}
    if osm_data.ROAD_INDEX is not None:
        nearest = osm_data.ROAD_INDEX.nearest_by_class(lat, lon, ROAD_SEARCH_M)

    for road in verified_roads or []:
        road_lat = to_finite_number(road.get("latitude"))
        road_lon = to_finite_number(road.get("longitude"))
        if road_lat is None or road_lon is None:
            continue
        road_class = normalize_osm_value(road.get("road_class") or road.get("feature_subtype")) or "unclassified"
        if road_class in ROAD_IGNORED_CLASSES or road_class not in ROAD_CLASS_VALUES:
            continue
        distance_m = calculate_distance(lat, lon, road_lat, road_lon)
        if distance_m <= ROAD_SEARCH_M and (road_class not in nearest or distance_m < nearest[road_class][0]):
            nearest[road_class] = (distance_m, str(road.get("name") or "").strip() or None)

    return nearest


def _best_road(nearest_roads, value_function, classes=None):
    """(value 0-1, road class, distance_m, name) of the road worth the most."""
    best = (0.0, None, None, None)
    for road_class, (distance_m, name) in sorted(nearest_roads.items()):
        if classes is not None and road_class not in classes:
            continue
        value = ROAD_CLASS_VALUES[road_class] * value_function(distance_m)
        if value > best[0]:
            best = (value, road_class, distance_m, name)
    return best


def _describe_road(road_class, distance_m, name):
    label = road_class.replace("_", " ")
    return f"{name or 'Unnamed road'} ({label}) {round(distance_m)} m"


def _score_road_access(lat, lon, verified_roads=None):
    """Two things matter: reaching a major road, and the road right at the site.
    Both take the best road in range, never simply the nearest one."""
    if osm_data.ROAD_INDEX is None and not verified_roads:
        return _unavailable_factor(
            "Road Data Unavailable",
            "The road network couldn't be loaded, so road access was left out of this score.",
            road_class=None,
            road_name=None,
            distance_m=None,
        )

    nearest = _nearest_roads(lat, lon, verified_roads)
    major_value, major_class, major_distance, major_name = _best_road(nearest, road_major_value, ROAD_MAJOR_CLASSES)
    front_value, front_class, front_distance, front_name = _best_road(nearest, road_frontage_value)

    raw_score = FACTOR_MAX * (ROAD_MAJOR_SHARE * major_value + ROAD_FRONTAGE_SHARE * front_value)
    status = _status_for(
        raw_score,
        ("Excellent Road Access", "Good Road Access", "Moderate Road Access", "Limited Road Access", "Poor Road Access"),
    )

    parts = []
    if major_class:
        parts.append(f"Major road: {_describe_road(major_class, major_distance, major_name)}")
    if front_class:
        parts.append(f"At the site: {_describe_road(front_class, front_distance, front_name)}")
    evidence = "; ".join(parts) + "." if parts else f"No usable road within {int(ROAD_SEARCH_M)} m."

    best_class, best_distance, best_name = (
        (front_class, front_distance, front_name) if front_class else (major_class, major_distance, major_name)
    )
    return _factor(
        raw_score,
        status,
        (
            f"{int(ROAD_MAJOR_SHARE * 100)}% of this score is how close a major road is, full value within "
            f"250 m and fading out by 1 km. The other {int(ROAD_FRONTAGE_SHARE * 100)}% is the road right at "
            "the site, where bigger roads count for more. Footpaths don't count."
        ),
        evidence,
        road_class=best_class,
        road_name=best_name,
        distance_m=round(best_distance, 2) if best_distance is not None else None,
        major_road={"class": major_class, "name": major_name, "distance_m": round(major_distance, 2)} if major_class else None,
    )


# ---- anchors --------------------------------------------------------------------

def _score_anchor_proximity(lat, lon, profile, anchors):
    """Each anchor adds its power, at full value inside its category's band and fading
    to nothing beyond it. Extra anchors add less and less, so a busy area can't exceed the maximum."""
    if anchors is None:
        return _unavailable_factor(
            "Anchor Data Unavailable",
            "The anchors couldn't be loaded, so traffic generators were left out of this score.",
            weighted_anchor_power=0.0,
            anchors_found=[],
            nearby_anchors=[],
        )

    total_power = 0.0
    nearby = []
    for anchor in anchors:
        anchor_lat = to_finite_number(anchor.get("lat"))
        anchor_lon = to_finite_number(anchor.get("lon"))
        if anchor_lat is None or anchor_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, anchor_lat, anchor_lon)
        if distance_m >= anchor_reach_m(anchor.get("category")):
            continue

        contribution = float(anchor.get("power") or 0.0) * anchor_value(distance_m, anchor.get("category"))
        if contribution <= 0.0:
            continue

        total_power += contribution
        nearby.append({
            "name": anchor.get("name"),
            "category": anchor.get("category"),
            "lat": anchor_lat,
            "lon": anchor_lon,
            "distance_m": round(distance_m, 2),
            "power": anchor.get("power"),
            "contribution": round(contribution, 2),
            "source": anchor.get("origin") or "osm",
        })

    nearby.sort(key=lambda item: (-item["contribution"], item["distance_m"], item["name"] or ""))
    target_power = float(profile.get("anchor_target_power") or 36.0) * ANCHOR_TARGET_SCALE
    raw_score = FACTOR_MAX * (1.0 - math.exp(-total_power / max(1.0, target_power)))
    status = _status_for(
        raw_score,
        ("Strong Traffic Generators", "Moderate Traffic Generators", "Mixed Traffic Support", "Weak Traffic Support", "Low Visibility"),
    )

    if nearby:
        top = ", ".join(f"{item['name']} ({round(item['distance_m'])} m)" for item in nearby[:3])
        more = f" and {len(nearby) - 3} more" if len(nearby) > 3 else ""
        evidence = f"{len(nearby)} anchor{'s' if len(nearby) != 1 else ''} counted: {top}{more}."
    else:
        evidence = "No anchors close enough to count."

    return _factor(
        raw_score,
        status,
        (
            "Anchors are places that bring people to an area, like markets, schools and terminals. Each counts "
            "fully within its usual walking distance (300-500 m by type) and fades out beyond that. "
            f"Their combined pull here is {total_power:.1f}."
        ),
        evidence,
        weighted_anchor_power=round(total_power, 3),
        anchors_found=[item["name"] for item in nearby if item["name"]],
        nearby_anchors=nearby,
    )


# ---- building density -----------------------------------------------------------

def _score_building_density(lat, lon, verified_buildings=None):
    if osm_data.BUILDING_INDEX is None and not verified_buildings:
        return _unavailable_factor(
            "Building Data Unavailable",
            "Building footprints couldn't be loaded, so building density was left out of this score.",
            weighted_intensity=0.0,
            feature_count=0,
        )

    intensity = 0.0
    feature_count = 0
    if osm_data.BUILDING_INDEX is not None:
        intensity, feature_count = osm_data.BUILDING_INDEX.intensity(lat, lon, BUILDING_REACH_M)

    for building in verified_buildings or []:
        building_lat = to_finite_number(building.get("latitude"))
        building_lon = to_finite_number(building.get("longitude"))
        if building_lat is None or building_lon is None:
            continue
        pull = building_pull(calculate_distance(lat, lon, building_lat, building_lon))
        if pull <= 0.0:
            continue
        area_m2 = to_finite_number(building.get("area_m2")) or 0.0
        intensity += pull * (1.0 + min(2.0, area_m2 / 2500.0) * 0.18)
        feature_count += 1

    raw_score = _clamp_score(BUILDING_CURVE * math.log1p(intensity * BUILDING_SCALE), 0, FACTOR_MAX)
    status = _status_for(
        raw_score,
        ("Dense Built Environment", "Moderately Built-Up", "Balanced Built Form", "Sparse Built Form", "Very Sparse Built Form"),
    )
    reach = int(BUILDING_REACH_M)
    return _factor(
        raw_score,
        status,
        (
            f"This measures how built-up the area is, using mapped buildings and land uses within {reach} m. "
            "Closer and larger ones count for more. It is an estimate of nearby activity, not a head count."
        ),
        f"{feature_count} mapped building{'s' if feature_count != 1 else ''} and land uses within {reach} m.",
        weighted_intensity=round(intensity, 3),
        feature_count=feature_count,
    )


# ---- competitor gathering -------------------------------------------------------

def _is_same_competitor(existing, candidate, distance_m):
    if candidate.get("osm_ref") and existing.get("osm_ref") == candidate.get("osm_ref"):
        return True
    if distance_m > COMPETITOR_DEDUPE_M:
        return False
    # An unnamed entry this close to a known one is most likely the same shop.
    if not candidate.get("name") or not existing.get("name"):
        return True
    return str(existing["name"]).strip().lower() == str(candidate["name"]).strip().lower()


def _add_competitor(found, item, origin_lat, origin_lon, reach_m, source):
    item_lat = to_finite_number(item.get("lat", item.get("latitude")))
    item_lon = to_finite_number(item.get("lon", item.get("longitude")))
    if item_lat is None or item_lon is None:
        return

    distance_m = calculate_distance(origin_lat, origin_lon, item_lat, item_lon)
    if distance_m > reach_m:
        return

    candidate = {
        "lat": item_lat,
        "lon": item_lon,
        "name": str(item.get("name")).strip() if item.get("name") else None,
        "source": source,
        "distance_m": distance_m,
        "osm_ref": item.get("osm_ref"),
    }
    for existing in found:
        gap_m = calculate_distance(existing["lat"], existing["lon"], item_lat, item_lon)
        if _is_same_competitor(existing, candidate, gap_m):
            return
    found.append(candidate)


def _gather_competitors(lat, lon, reach_m, business_key, profile, cursor, warnings):
    """Competitors within reach_m, one entry per shop. Admin records go first, so they win a duplicate."""
    found = []
    database_ok = True

    try:
        for shop in fetch_verified_local_features("msme", business_type=business_key, cursor=cursor, strict=True):
            _add_competitor(found, shop, lat, lon, reach_m, "verified_local")
        for shop in fetch_custom_msmes(business_key, cursor=cursor, strict=True):
            _add_competitor(found, shop, lat, lon, reach_m, "custom_msme")
    except Exception as exc:
        database_ok = False
        print(f"Competitor records could not be read: {exc}")
        warnings.append("Admin-added competitors couldn't be read, so only OpenStreetMap competitors were counted.")

    osm_tags = profile.get("osm_tags") or SME_DATABASE.get(business_key, {}).get("osm_tags") or []
    for tag_key, tag_value in osm_tags:
        for competitor in get_cached_pbf_competitors(tag_key, tag_value):
            _add_competitor(found, competitor, lat, lon, reach_m, "osm")
    for competitor in get_name_keyword_pbf_competitors(business_key):
        _add_competitor(found, competitor, lat, lon, reach_m, "osm")

    if not osm_data.PBF_FEATURES_AVAILABLE and database_ok:
        warnings.append("OpenStreetMap shops couldn't be loaded, so only admin-added competitors were counted.")

    return found, (database_ok or osm_data.PBF_FEATURES_AVAILABLE)


def count_known_competitors(business_key, cursor=None):
    """How many shops of this type are on record citywide, one count per shop.
    With no limit on the reach, the point it measures from makes no difference."""
    found, _ = _gather_competitors(0.0, 0.0, math.inf, business_key, _get_analysis_profile(business_key), cursor, [])
    return len(found)


def _for_map(competitors, radius_meters, default_name):
    """What the map lists: the competitors inside the chosen view radius."""
    return [
        {
            "lat": item["lat"],
            "lon": item["lon"],
            "name": item["name"] or default_name,
            "source": item["source"],
            "distance_m": round(item["distance_m"], 2),
        }
        for item in sorted(competitors, key=lambda item: item["distance_m"])
        if item["distance_m"] <= radius_meters
    ]


# ---- the composite market score -------------------------------------------------

def demand_share(components, weights):
    """How much customer demand is nearby, 0-1, from the factors that stand in for it.
    When none of them could be loaded it returns 1, so the competition score isn't
    cut because of missing data; the report already flags the missing factors."""
    available = [key for key in DEMAND_FACTORS if components[key]["available"]]
    total_weight = sum(weights[key] for key in available)
    if total_weight <= 0:
        return 1.0
    return sum(components[key]["raw_score"] * weights[key] for key in available) / (total_weight * FACTOR_MAX)


def apply_demand_credit(competition, share):
    """Adds what the competition score counts for in the total. The factor's own score
    still says how crowded the area is, so the report can show both."""
    if not competition["available"]:
        return competition
    credited = competition["raw_score"] * share
    competition["credited_raw_score"] = credited
    competition["credited_score"] = round(credited, 1)
    competition["demand_share"] = round(share, 3)
    if share < 0.995:
        competition["evidence"] += (
            f" Counted at {round(share * 100)}%, because low competition only helps where customers are nearby."
        )
    return competition


def combine_market_factors(components, weights):
    """Weighted average of the available factors; an unavailable one is left out and
    the remaining weights are rescaled. Returns (raw score or None, {factor: weight used})."""
    available = {key: weight for key, weight in weights.items() if components[key]["available"]}
    total_weight = sum(available.values())
    if total_weight <= 0:
        return None, {}
    used_weights = {key: weight / total_weight for key, weight in available.items()}
    raw_score = sum(
        components[key].get("credited_raw_score", components[key]["raw_score"]) * used_weights[key]
        for key in used_weights
    )
    return raw_score, used_weights


def _market_weights(profile_key, profile):
    ahp = get_ahp_weights("saturation", profile_key)
    if ahp:
        vector = ahp["priority_vector"]
        return dict(zip(AHP_MARKET_LABELS, vector)), ahp
    return {
        "competition": float(profile.get("competition_weight") or 0.42),
        "road": float(profile.get("road_weight") or 0.23),
        "anchor": float(profile.get("anchor_weight") or 0.20),
        "building": float(profile.get("building_weight") or 0.15),
    }, None


def evaluate_layered_market_context(lat, lon, radius_meters, business_type):
    profile_key = normalize_osm_value(business_type) or ""
    profile = MSME_CATEGORY_PROFILES.get(profile_key, DEFAULT_MSME_ANALYSIS_PROFILE)
    default_name = profile.get("display_name") or "MSME"
    warnings = []

    # Wait for the OSM data rather than scoring without it. Each returns at once when
    # it is already loaded, and waits when the startup thread is still loading it.
    osm_data.preload_pbf_competitor_cache()
    osm_data.preload_pbf_spatial_context_cache()

    # One connection for all the lookups below. Autocommit so one failed statement
    # can't abort the others. If it can't open, each lookup tries its own connection.
    shared_conn = None
    shared_cursor = None
    try:
        shared_conn = psycopg2.connect(**DB_CONFIG)
        shared_conn.autocommit = True
        shared_cursor = shared_conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(shared_cursor)
    except Exception as exc:
        print(f"Shared DB connection for market context failed, falling back to per-call connections: {exc}")
        shared_conn = None
        shared_cursor = None

    verified_roads = []
    verified_buildings = []
    try:
        try:
            verified_roads = fetch_verified_local_features("road", cursor=shared_cursor, strict=True)
            verified_buildings = fetch_verified_local_features("building", cursor=shared_cursor, strict=True)
        except Exception as exc:
            print(f"Verified road/building records could not be read: {exc}")
            warnings.append("Admin-verified roads and buildings couldn't be read, so only OpenStreetMap data was used for them.")

        anchors, anchor_warnings = get_scoring_anchors(shared_cursor)
        warnings.extend(anchor_warnings)

        competitors, competitors_available = _gather_competitors(
            lat, lon, max(COMPETITION_REACH_M, float(radius_meters or 0)), profile_key, profile, shared_cursor, warnings,
        )
    finally:
        if shared_cursor is not None:
            shared_cursor.close()
        if shared_conn is not None:
            shared_conn.close()

    if competitors_available:
        competition_density = _score_competitor_density(lat, lon, competitors, profile)
    else:
        competition_density = _unavailable_factor(
            "Competitor Data Unavailable",
            "Neither OpenStreetMap shops nor admin records could be read, so competition was left out of this score.",
            weighted_pressure=0.0,
            competitor_count=0,
        )
    road_access = _score_road_access(lat, lon, verified_roads=verified_roads)
    anchor_proximity = _score_anchor_proximity(lat, lon, profile, anchors)
    building_density = _score_building_density(lat, lon, verified_buildings=verified_buildings)

    components = {
        "competition": competition_density,
        "road": road_access,
        "anchor": anchor_proximity,
        "building": building_density,
    }
    weights, ahp_market = _market_weights(profile_key, profile)
    apply_demand_credit(competition_density, demand_share(components, weights))
    market_raw, used_weights = combine_market_factors(components, weights)

    if market_raw is None:
        saturation = _unavailable_factor(
            "Market Data Unavailable",
            "None of the market factors could be loaded for this scan.",
        )
    else:
        saturation = _factor(
            market_raw,
            _status_for(
                market_raw,
                ("Strong Market Potential", "Good Market Potential", "Moderate Market Potential", "Weak Market Potential", "Poor Market Potential"),
            ),
            (
                f"Market potential combines competition, road access, anchors and building density for {default_name}, "
                "using the AHP weights for this business type."
            ),
            f"Combined from {len(used_weights)} of 4 market factors.",
        )
    saturation["description"] = f"Combined market potential for {default_name}"

    ahp_market_methodology = {
        "source": "ahp" if ahp_market else "static_fallback",
        "provenance": (ahp_market or {}).get("updated_by_admin_email"),
        "criteria_labels": AHP_MARKET_LABELS,
        "pairwise_matrix": (ahp_market or {}).get("pairwise_matrix"),
        "priority_vector": [weights[label] for label in AHP_MARKET_LABELS],
        "lambda_max": (ahp_market or {}).get("lambda_max"),
        "consistency_index": (ahp_market or {}).get("ci"),
        "random_index": (ahp_market or {}).get("ri"),
        "consistency_ratio": (ahp_market or {}).get("cr"),
        "is_consistent": (ahp_market or {}).get("is_consistent"),
    }

    return {
        "profile": profile,
        "competitors": _for_map(competitors, radius_meters, default_name),
        "competition_density": competition_density,
        "road_access": road_access,
        "anchor_proximity": anchor_proximity,
        "building_density": building_density,
        "market_weights_used": used_weights,
        "warnings": warnings,
        "ahp_sub_criteria_methodology": ahp_market_methodology,
        "saturation": saturation,
    }


def collect_competitor_preview(lat, lon, radius_meters, business_type):
    profile_key = normalize_osm_value(business_type) or ""
    profile = MSME_CATEGORY_PROFILES.get(profile_key, DEFAULT_MSME_ANALYSIS_PROFILE)
    default_name = profile.get("display_name") or "MSME"

    competitors, _ = _gather_competitors(lat, lon, float(radius_meters), profile_key, profile, None, [])
    locations = _for_map(competitors, radius_meters, default_name)

    return {
        "business_type": profile_key,
        "business_label": default_name,
        "target_coords": {"lat": lat, "lng": lon},
        "radius_meters": radius_meters,
        "competitors_found": len(locations),
        "competitor_locations": locations,
    }
