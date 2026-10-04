"""OpenStreetMap (panabo.pbf) caches: competitors, roads, and buildings."""
from threading import Lock

from constants.msme import (
    COMMERCIAL_AMENITY_VALUES,
    PBF_NAME_KEYWORD_FALLBACK,
    ROAD_CLASS_BASE_SCORES,
)
from core.paths import PBF_PATH
from utils.geo import calculate_distance
from utils.geo_libs import gpd
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
