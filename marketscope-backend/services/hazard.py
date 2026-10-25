"""
Flood hazard layer: loads the active hazard map layer once and scores a point.

The layer lives in the map_layers table (services/map_layers.py). Each polygon
carries a zone_class that maps to a flood level:
Var 1 = Very High, Var 2 = High, Var 3 = Moderate.
"""
from threading import Lock

from constants.map_layers import HAZARD_CLASS_VARS
from db.map_layer_queries import get_active_layer, open_map_layer_cursor
from utils.geo_libs import Point, shape, unary_union


HAZARD_LAYER_CACHE = []


HAZARD_LAYER_CACHE_LOADED = False


HAZARD_LAYER_LOCK = Lock()


HAZARD_LAYER_SOURCE = None


HAZARD_LAYER_LABELS = {
    1: {"name": "Very High Flood Hazard (5-Year Return Period)", "score": 5},
    2: {"name": "High Flood Hazard (5-Year Return Period)", "score": 12},
    3: {"name": "Moderate Flood Hazard (5-Year Return Period)", "score": 18},
}


def _load_active_hazard_geometries():
    """(layer name, {var: [geometries]}) for the active hazard layer, or (None, {})."""
    with open_map_layer_cursor() as cursor:
        layer = get_active_layer(cursor, "hazard")
    if not layer:
        return None, {}

    raw_geometries_by_var = {}
    for feature in (layer["geojson"] or {}).get("features") or []:
        hazard_var = HAZARD_CLASS_VARS.get((feature.get("properties") or {}).get("zone_class"))
        if hazard_var is None:
            continue
        try:
            geometry = shape(feature["geometry"])
        except Exception:
            continue
        if geometry.is_empty:
            continue
        raw_geometries_by_var.setdefault(hazard_var, []).append(geometry)
    return layer["name"], raw_geometries_by_var


def preload_hazard_layer_cache():
    global HAZARD_LAYER_CACHE, HAZARD_LAYER_CACHE_LOADED, HAZARD_LAYER_SOURCE

    if HAZARD_LAYER_CACHE_LOADED:
        return

    if Point is None or shape is None or unary_union is None:
        HAZARD_LAYER_CACHE = []
        HAZARD_LAYER_SOURCE = None
        HAZARD_LAYER_CACHE_LOADED = True
        print("Hazard layer cache skipped: shapely is unavailable")
        return

    with HAZARD_LAYER_LOCK:
        if HAZARD_LAYER_CACHE_LOADED:
            return

        try:
            layer_name, raw_geometries_by_var = _load_active_hazard_geometries()
        except Exception as e:
            # Leave the cache unloaded so the next call retries (e.g. the database was not up yet).
            print(f"Hazard layer load warning: {e}")
            return

        cache = []

        # Remove overlaps by hazard priority so each point belongs to at most one flood class.
        covered_geometry = None
        for hazard_var, label in sorted(HAZARD_LAYER_LABELS.items(), key=lambda item: item[1]["score"]):
            var_geometries = raw_geometries_by_var.get(hazard_var, [])
            if not var_geometries:
                continue

            try:
                merged_geometry = unary_union(var_geometries)
            except Exception:
                continue

            if merged_geometry is None or merged_geometry.is_empty:
                continue

            exclusive_geometry = merged_geometry
            if covered_geometry is not None and not covered_geometry.is_empty:
                exclusive_geometry = merged_geometry.difference(covered_geometry)

            if exclusive_geometry is None or exclusive_geometry.is_empty:
                continue

            cache.append({
                "var": hazard_var,
                "name": label["name"],
                "score": label["score"],
                "geometry": exclusive_geometry,
            })

            covered_geometry = (
                exclusive_geometry
                if covered_geometry is None
                else covered_geometry.union(exclusive_geometry)
            )

        cache.sort(key=lambda item: item["score"])
        HAZARD_LAYER_CACHE = cache
        HAZARD_LAYER_SOURCE = layer_name
        HAZARD_LAYER_CACHE_LOADED = True
        if HAZARD_LAYER_CACHE:
            print(f"Hazard layer cache loaded: {len(HAZARD_LAYER_CACHE)} flood classes from layer '{HAZARD_LAYER_SOURCE}'")
        else:
            print("Hazard layer cache loaded with no active hazard layer")


def reload_hazard_layer_cache():
    """Drop the cache and load the (new) active hazard layer."""
    global HAZARD_LAYER_CACHE_LOADED
    with HAZARD_LAYER_LOCK:
        HAZARD_LAYER_CACHE_LOADED = False
    preload_hazard_layer_cache()


def evaluate_hazard(lat, lon):
    preload_hazard_layer_cache()

    hazard_score = 25
    hazard_status = "Low Risk / Safe"
    hazard_matches = []

    if HAZARD_LAYER_CACHE and Point is not None:
        location_point = Point(lon, lat)

        for feature in HAZARD_LAYER_CACHE:
            try:
                if feature["geometry"].intersects(location_point):
                    match_name = f"{feature['name']} (Flood)"
                    hazard_matches.append(match_name)
                    hazard_score = feature["score"]
                    hazard_status = match_name
                    break
            except Exception:
                continue

    return hazard_score, hazard_status, hazard_matches
