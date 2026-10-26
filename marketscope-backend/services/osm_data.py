"""OpenStreetMap (panabo.pbf) caches: competitors, roads, buildings, and the reference road map."""
import json
from threading import Lock

from constants.geo import PANABO_BOUNDS
from constants.msme import (
    COMMERCIAL_AMENITY_VALUES,
    PBF_NAME_KEYWORD_FALLBACK,
    ROAD_CLASS_BASE_SCORES,
)
from core.paths import PBF_PATH
from utils.geo import calculate_distance
from utils.geo_libs import box, gpd, mapping
from utils.values import normalize_osm_value, to_finite_number


PBF_COMPETITOR_CACHE = {}


PBF_ALL_COMPETITORS = []


PBF_CACHE_LOADED = False


PBF_CACHE_LOCK = Lock()


PBF_LAYERS = ["points", "multipolygons", "lines", "multilinestrings"]


PBF_SEARCH_COLUMNS = ["amenity", "shop", "healthcare"]


PBF_ROAD_CONTEXT_GDF = None


PBF_BUILDING_CONTEXT_GDF = None


PBF_SPATIAL_CONTEXT_LOADED = False


PBF_SPATIAL_CONTEXT_LOCK = Lock()


def _normalize_road_class(value):
    normalized = normalize_osm_value(value)
    if normalized is None:
        return None

    normalized = normalized.replace("-", "_")
    normalized = normalized.replace(" ", "_")
    normalized = normalized.replace("__", "_")

    if normalized.endswith("_link"):
        normalized = normalized[:-5]

    if normalized in ROAD_CLASS_BASE_SCORES:
        return normalized

    if normalized in {"road", "street", "lane"}:
        return "unclassified"
    if normalized in {"main", "main_road", "major_road"}:
        return "primary"
    return None


def _feature_weight_from_building_row(row):
    building_value = normalize_osm_value(row.get("building"))
    landuse_value = normalize_osm_value(row.get("landuse"))
    amenity_value = normalize_osm_value(row.get("amenity"))
    shop_value = normalize_osm_value(row.get("shop"))
    office_value = normalize_osm_value(row.get("office"))

    weight = 1.0

    if building_value in {"commercial", "retail", "industrial", "public", "university", "hospital", "school", "office"}:
        weight *= 1.20
    elif building_value in {"house", "residential", "apartments", "roof"}:
        weight *= 0.86

    if landuse_value in {"commercial", "retail"}:
        weight *= 1.28
    elif landuse_value == "industrial":
        weight *= 1.14
    elif landuse_value == "residential":
        weight *= 0.88

    if amenity_value in {"marketplace", "hospital", "school", "college", "university", "fuel", "parking", "restaurant", "fast_food", "cafe"}:
        weight *= 1.12

    if shop_value:
        weight *= 1.10

    if office_value:
        weight *= 1.05

    return weight


def preload_pbf_spatial_context_cache():
    global PBF_ROAD_CONTEXT_GDF, PBF_BUILDING_CONTEXT_GDF, PBF_SPATIAL_CONTEXT_LOADED

    if PBF_SPATIAL_CONTEXT_LOADED:
        return

    if gpd is None:
        PBF_ROAD_CONTEXT_GDF = None
        PBF_BUILDING_CONTEXT_GDF = None
        PBF_SPATIAL_CONTEXT_LOADED = True
        print("PBF spatial context cache skipped: geopandas is unavailable")
        return

    with PBF_SPATIAL_CONTEXT_LOCK:
        if PBF_SPATIAL_CONTEXT_LOADED:
            return

        if not PBF_PATH.exists():
            PBF_ROAD_CONTEXT_GDF = None
            PBF_BUILDING_CONTEXT_GDF = None
            PBF_SPATIAL_CONTEXT_LOADED = True
            print(f"PBF spatial context cache skipped: file not found at {PBF_PATH}")
            return

        road_gdf = None
        building_gdf = None

        try:
            road_gdf = gpd.read_file(str(PBF_PATH), layer="lines", engine="pyogrio")
        except Exception as exc:
            print(f"PBF road context read skipped: {exc}")

        if road_gdf is not None and not road_gdf.empty and "geometry" in road_gdf.columns and "highway" in road_gdf.columns:
            road_gdf = road_gdf[road_gdf["geometry"].notna() & road_gdf["highway"].notna()].copy()
            road_gdf["road_class"] = road_gdf["highway"].apply(_normalize_road_class)
            road_gdf = road_gdf[road_gdf["road_class"].notna()].copy()
            road_gdf["road_base_score"] = road_gdf["road_class"].map(ROAD_CLASS_BASE_SCORES).fillna(10)
            PBF_ROAD_CONTEXT_GDF = road_gdf[["name", "highway", "road_class", "road_base_score", "geometry"]].copy()
        else:
            PBF_ROAD_CONTEXT_GDF = None

        try:
            building_gdf = gpd.read_file(str(PBF_PATH), layer="multipolygons", engine="pyogrio")
        except Exception as exc:
            print(f"PBF building context read skipped: {exc}")

        if building_gdf is not None and not building_gdf.empty and "geometry" in building_gdf.columns:
            context_columns = [col for col in ["name", "building", "landuse", "amenity", "shop", "office", "geometry"] if col in building_gdf.columns]
            building_gdf = building_gdf[context_columns].copy()
            context_mask = False
            for col in ["building", "landuse", "amenity", "shop", "office"]:
                if col in building_gdf.columns:
                    context_mask = context_mask | building_gdf[col].notna()
            building_gdf = building_gdf[context_mask & building_gdf["geometry"].notna()].copy()
            if not building_gdf.empty:
                building_gdf["feature_weight"] = building_gdf.apply(_feature_weight_from_building_row, axis=1)
                PBF_BUILDING_CONTEXT_GDF = building_gdf[["name", "building", "landuse", "amenity", "shop", "office", "feature_weight", "geometry"]].copy()
            else:
                PBF_BUILDING_CONTEXT_GDF = None
        else:
            PBF_BUILDING_CONTEXT_GDF = None

        PBF_SPATIAL_CONTEXT_LOADED = True
        print(
            "PBF spatial context loaded: "
            f"roads={0 if PBF_ROAD_CONTEXT_GDF is None else len(PBF_ROAD_CONTEXT_GDF)}, "
            f"buildings={0 if PBF_BUILDING_CONTEXT_GDF is None else len(PBF_BUILDING_CONTEXT_GDF)}"
        )


def preload_pbf_competitor_cache():
    global PBF_COMPETITOR_CACHE, PBF_ALL_COMPETITORS, PBF_CACHE_LOADED

    if PBF_CACHE_LOADED:
        return

    if gpd is None:
        PBF_COMPETITOR_CACHE = {}
        PBF_ALL_COMPETITORS = []
        PBF_CACHE_LOADED = True
        print("PBF cache skipped: geopandas is unavailable")
        return

    with PBF_CACHE_LOCK:
        if PBF_CACHE_LOADED:
            return

        cache = {}
        all_competitors = []

        if not PBF_PATH.exists():
            PBF_COMPETITOR_CACHE = cache
            PBF_ALL_COMPETITORS = all_competitors
            PBF_CACHE_LOADED = True
            print(f"PBF cache skipped: file not found at {PBF_PATH}")
            return

        for layer in PBF_LAYERS:
            try:
                gdf = gpd.read_file(str(PBF_PATH), layer=layer, engine="pyogrio")
            except Exception:
                continue

            available_columns = [col for col in PBF_SEARCH_COLUMNS if col in gdf.columns]
            if not available_columns or "geometry" not in gdf.columns:
                continue

            for col in available_columns:
                matches = gdf[gdf[col].notna()]
                for _, row in matches.iterrows():
                    geometry = row.geometry
                    if geometry is None:
                        continue

                    search_key = normalize_osm_value(row[col])
                    if not search_key:
                        continue

                    centroid = geometry.centroid
                    competitor_entry = {
                        "lat": centroid.y,
                        "lon": centroid.x,
                        "name": row.get("name"),
                        "tag_key": col,
                        "tag_value": search_key,
                    }

                    cache.setdefault(search_key, []).append(competitor_entry)
                    all_competitors.append(competitor_entry)

        PBF_COMPETITOR_CACHE = cache
        PBF_ALL_COMPETITORS = all_competitors
        PBF_CACHE_LOADED = True
        print(f"PBF cache loaded for {len(cache)} business values and {len(all_competitors)} features")


def get_cached_pbf_competitors(search_value):
    if not PBF_CACHE_LOADED:
        preload_pbf_competitor_cache()
    return PBF_COMPETITOR_CACHE.get(normalize_osm_value(search_value), [])


def get_name_keyword_pbf_competitors(business_type):
    if not PBF_CACHE_LOADED:
        preload_pbf_competitor_cache()

    business_key = normalize_osm_value(business_type) or ""
    keywords = PBF_NAME_KEYWORD_FALLBACK.get(business_key, [])
    if not keywords:
        return []

    matches = []
    for item in PBF_ALL_COMPETITORS:
        name = str(item.get("name") or "").strip().lower()
        if not name:
            continue
        if any(keyword in name for keyword in keywords):
            matches.append(item)

    return matches


def get_generic_nearby_pbf_competitors(lat, lon, radius_meters, limit=80):
    if not PBF_CACHE_LOADED:
        preload_pbf_competitor_cache()

    nearby = []
    for item in PBF_ALL_COMPETITORS:
        name = str(item.get("name") or "").strip()
        if not name:
            continue

        tag_key = normalize_osm_value(item.get("tag_key"))
        tag_value = normalize_osm_value(item.get("tag_value"))
        if tag_key == "shop":
            pass
        elif tag_key == "healthcare":
            pass
        elif tag_key == "amenity" and tag_value in COMMERCIAL_AMENITY_VALUES:
            pass
        else:
            continue

        item_lat = to_finite_number(item.get("lat"))
        item_lon = to_finite_number(item.get("lon"))
        if item_lat is None or item_lon is None:
            continue

        if calculate_distance(lat, lon, item_lat, item_lon) <= radius_meters:
            nearby.append(item)
            if len(nearby) >= limit:
                break

    return nearby


# ---- reference road map (admin Map Layer Studio "Roads only" view) ----------------

REFERENCE_MAP_JSON = None


REFERENCE_MAP_LOCK = Lock()


REFERENCE_MAJOR_ROADS = {"motorway", "trunk", "primary", "secondary"}


REFERENCE_PATHS = {"track", "path", "footway", "pedestrian", "cycleway", "steps", "bridleway"}


REFERENCE_SKIPPED_ROADS = {"construction", "proposed", "platform", "raceway", "bus_stop"}


REFERENCE_WATERWAYS = {"river", "stream", "canal", "drain", "ditch"}


# OSM place types: Panabo's barangays are mapped as suburb/village/quarter,
# subdivisions and puroks as neighbourhood/hamlet.
REFERENCE_BARANGAY_PLACES = {"suburb", "village", "quarter", "town"}


REFERENCE_AREA_PLACES = {"neighbourhood", "hamlet", "isolated_dwelling"}


def _round_coordinates(value):
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], float):
            return [round(number, 6) for number in value]
        return [_round_coordinates(item) for item in value]
    return value


def _reference_road_class(highway):
    highway = normalize_osm_value(highway)
    if not highway or highway in REFERENCE_SKIPPED_ROADS:
        return None
    if highway.endswith("_link"):
        highway = highway[:-5]
    if highway in REFERENCE_MAJOR_ROADS:
        return "major"
    if highway in REFERENCE_PATHS:
        return "path"
    return "minor"


def get_reference_map_json():
    """Roads, waterways and place names around Panabo as compact GeoJSON text (cached).

    Feature properties: kind ("road" | "water" | "place"), cls (major/minor/path,
    the waterway type, or barangay/area for places) and name. Used for the plain
    road map in the admin map editor and the satellite view's labels.
    """
    global REFERENCE_MAP_JSON
    if REFERENCE_MAP_JSON is not None:
        return REFERENCE_MAP_JSON
    if gpd is None or not PBF_PATH.exists():
        return None

    with REFERENCE_MAP_LOCK:
        if REFERENCE_MAP_JSON is not None:
            return REFERENCE_MAP_JSON

        lines = gpd.read_file(str(PBF_PATH), layer="lines", engine="pyogrio")
        pad = 0.01
        clip = box(PANABO_BOUNDS[2] - pad, PANABO_BOUNDS[0] - pad, PANABO_BOUNDS[3] + pad, PANABO_BOUNDS[1] + pad)

        features = []
        for _, row in lines.iterrows():
            geometry = row.geometry
            if geometry is None or geometry.is_empty:
                continue

            road_class = _reference_road_class(row.get("highway")) if "highway" in lines.columns else None
            waterway = normalize_osm_value(row.get("waterway")) if "waterway" in lines.columns else None
            if road_class:
                properties = {"kind": "road", "cls": road_class}
            elif waterway in REFERENCE_WATERWAYS:
                properties = {"kind": "water", "cls": waterway}
            else:
                continue

            geometry = geometry.intersection(clip)
            if geometry.is_empty or geometry.geom_type not in ("LineString", "MultiLineString"):
                continue
            geometry = geometry.simplify(0.00001)

            name = row.get("name")
            if isinstance(name, str) and name.strip():
                properties["name"] = name.strip()

            shape_json = mapping(geometry)
            features.append({
                "type": "Feature",
                "properties": properties,
                "geometry": {"type": shape_json["type"], "coordinates": _round_coordinates(shape_json["coordinates"])},
            })

        try:
            points = gpd.read_file(str(PBF_PATH), layer="points", engine="pyogrio")
        except Exception as exc:
            points = None
            print(f"Reference map place names skipped: {exc}")
        if points is not None and "place" in points.columns:
            for _, row in points[points["place"].notna() & points["name"].notna()].iterrows():
                place = normalize_osm_value(row.get("place"))
                if place in REFERENCE_BARANGAY_PLACES:
                    place_class = "barangay"
                elif place in REFERENCE_AREA_PLACES:
                    place_class = "area"
                else:
                    continue
                point = row.geometry
                if point is None or point.is_empty or not clip.contains(point):
                    continue
                features.append({
                    "type": "Feature",
                    "properties": {"kind": "place", "cls": place_class, "name": str(row.get("name")).strip()},
                    "geometry": {"type": "Point", "coordinates": [round(point.x, 6), round(point.y, 6)]},
                })

        REFERENCE_MAP_JSON = json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))
        print(f"Reference road map cached: {len(features)} features, {len(REFERENCE_MAP_JSON) // 1024} KB")
        return REFERENCE_MAP_JSON
