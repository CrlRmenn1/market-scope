"""Zoning layer: loads the active zoning map layer once and scores a point.

The layer lives in the map_layers table (services/map_layers.py). Each polygon
carries a zone_class from constants/map_layers.py ZONING_CLASSES, which sets
the zoning score. Where polygons overlap, the class with the best score wins.
"""
from threading import Lock

from constants.geo import INDUSTRIAL_ZONE_BUSINESSES
from constants.map_layers import ZONING_CLASSES
from db.map_layer_queries import get_active_layer, open_map_layer_cursor
from utils.geo_libs import Point, shape


ZONING_LAYER_CACHE = []  # [{"zone_class", "label", "geometry"}]


ZONING_LAYER_CACHE_LOADED = False


ZONING_LAYER_LOCK = Lock()


ZONING_LAYER_SOURCE = None


OUTSIDE_ZONES_STATUS = "Outside Commercial Zone"


NO_LAYER_STATUS = "No Zoning Layer Active"


def zoning_class_score(zone_class: str, business_key: str):
    """(score, status) a business gets inside a polygon of this class."""
    zone = ZONING_CLASSES[zone_class]
    if "other_score" in zone and business_key not in INDUSTRIAL_ZONE_BUSINESSES:
        return zone["other_score"], zone["other_status"]
    return zone["score"], zone["status"]


def features_to_zoning_cache(features):
    cache = []
    for feature in features or []:
        properties = feature.get("properties") or {}
        zone_class = properties.get("zone_class")
        if zone_class not in ZONING_CLASSES:
            continue
        try:
            geometry = shape(feature["geometry"])
        except Exception:
            continue
        if geometry.is_empty:
            continue
        cache.append({"zone_class": zone_class, "label": properties.get("label"), "geometry": geometry})
    return cache


def preload_zoning_layer_cache():
    global ZONING_LAYER_CACHE, ZONING_LAYER_CACHE_LOADED, ZONING_LAYER_SOURCE

    if ZONING_LAYER_CACHE_LOADED:
        return

    if Point is None or shape is None:
        ZONING_LAYER_CACHE = []
        ZONING_LAYER_SOURCE = None
        ZONING_LAYER_CACHE_LOADED = True
        print("Zoning layer cache skipped: shapely is unavailable")
        return

    with ZONING_LAYER_LOCK:
        if ZONING_LAYER_CACHE_LOADED:
            return

        try:
            with open_map_layer_cursor() as cursor:
                layer = get_active_layer(cursor, "zoning")
        except Exception as e:
            # Leave the cache unloaded so the next call retries (e.g. the database was not up yet).
            print(f"Zoning layer load warning: {e}")
            return

        ZONING_LAYER_CACHE = features_to_zoning_cache(((layer or {}).get("geojson") or {}).get("features"))
        ZONING_LAYER_SOURCE = layer["name"] if layer else None
        ZONING_LAYER_CACHE_LOADED = True
        if layer:
            print(f"Zoning layer cache loaded: {len(ZONING_LAYER_CACHE)} polygons from layer '{ZONING_LAYER_SOURCE}'")
        else:
            print("Zoning layer cache loaded with no active zoning layer")


def reload_zoning_layer_cache():
    """Drop the cache and load the (new) active zoning layer."""
    global ZONING_LAYER_CACHE_LOADED
    with ZONING_LAYER_LOCK:
        ZONING_LAYER_CACHE_LOADED = False
    preload_zoning_layer_cache()


def get_zoning_features():
    """The active zoning polygons (zone_class, label, shapely geometry)."""
    preload_zoning_layer_cache()
    return ZONING_LAYER_CACHE


def evaluate_zoning(lat, lon, business_key: str):
    """(score, status, zone_class or None) for a point and business type."""
    preload_zoning_layer_cache()

    if not ZONING_LAYER_SOURCE:
        return 0, NO_LAYER_STATUS, None

    location_point = Point(lon, lat)
    best = None
    for feature in ZONING_LAYER_CACHE:
        try:
            if not feature["geometry"].intersects(location_point):
                continue
        except Exception:
            continue
        score, status = zoning_class_score(feature["zone_class"], business_key)
        if best is None or score > best[0]:
            best = (score, status, feature["zone_class"])

    return best or (0, OUTSIDE_ZONES_STATUS, None)
