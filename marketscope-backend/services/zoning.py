"""Zoning layer: loads the active zoning map layer once and scores a point.

The layer lives in the map_layers table (services/map_layers.py). Each polygon
carries a zone_class: one of the LGU zones in constants/map_layers.py
ZONING_CLASSES. Where polygons overlap, the one on top of the layer's stack
wins (services/layer_stack.py).

Zoning is pass/fail: a business allowed in the zone (zoning_allowed_uses table,
edited by the admin) gets ZONING_ALLOWED_SCORE, otherwise 0.
"""
from threading import Lock

from constants.map_layers import DEFAULT_ZONING_ALLOWED_USES, ZONING_ALLOWED_SCORE, ZONING_CLASSES
from db.map_layer_queries import get_active_layer, list_zoning_allowed_uses, open_map_layer_cursor
from services.layer_stack import flatten_features
from utils.geo_libs import Point, shape


ZONING_LAYER_CACHE = []  # [{"zone_class", "label", "geometry"}], flattened, bottom to top


ZONING_LAYER_CACHE_LOADED = False


ZONING_LAYER_LOCK = Lock()


ZONING_LAYER_SOURCE = None


# zone_class -> frozenset of allowed business types. Starts as the defaults
# (so code without a database still works) and is replaced from the
# zoning_allowed_uses table whenever the zoning cache loads.
ZONING_ALLOWED_USES = {zone: frozenset(businesses) for zone, businesses in DEFAULT_ZONING_ALLOWED_USES.items()}


OUTSIDE_ZONES_STATUS = "Outside Mapped Zones"


NO_LAYER_STATUS = "No Zoning Layer Active"


def is_business_allowed(zone_class: str, business_key: str) -> bool:
    return business_key in ZONING_ALLOWED_USES.get(zone_class, frozenset())


def zoning_class_score(zone_class: str, business_key: str):
    """(score, status) a business gets inside a polygon of this zone."""
    label = ZONING_CLASSES[zone_class]["label"]
    if is_business_allowed(zone_class, business_key):
        return ZONING_ALLOWED_SCORE, f"Allowed in {label}"
    return 0, f"Not Allowed in {label}"


def allowed_zone_classes(business_key: str):
    """The zones this business type may operate in."""
    return {zone for zone, businesses in ZONING_ALLOWED_USES.items() if business_key in businesses}


def allowed_uses_from_rows(rows):
    allowed = {}
    for row in rows:
        allowed.setdefault(row["zone_class"], set()).add(row["business_type"])
    return {zone: frozenset(businesses) for zone, businesses in allowed.items()}


def features_to_zoning_cache(features):
    """Flattened zoning polygons: each keeps only the area no higher polygon covers."""
    known = [feature for feature in features or [] if (feature.get("properties") or {}).get("zone_class") in ZONING_CLASSES]
    return flatten_features(known)


def preload_zoning_layer_cache():
    global ZONING_LAYER_CACHE, ZONING_LAYER_CACHE_LOADED, ZONING_LAYER_SOURCE, ZONING_ALLOWED_USES

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
                allowed_rows = list_zoning_allowed_uses(cursor)
        except Exception as e:
            # Leave the cache unloaded so the next call retries (e.g. the database was not up yet).
            print(f"Zoning layer load warning: {e}")
            return

        ZONING_ALLOWED_USES = allowed_uses_from_rows(allowed_rows)
        ZONING_LAYER_CACHE = features_to_zoning_cache(((layer or {}).get("geojson") or {}).get("features"))
        ZONING_LAYER_SOURCE = layer["name"] if layer else None
        ZONING_LAYER_CACHE_LOADED = True
        if layer:
            print(f"Zoning layer cache loaded: {len(ZONING_LAYER_CACHE)} polygons from layer '{ZONING_LAYER_SOURCE}'")
        else:
            print("Zoning layer cache loaded with no active zoning layer")


def reload_zoning_layer_cache():
    """Drop the cache and load the (new) active zoning layer and allowed uses."""
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

    # Flattened polygons don't overlap; checking from the top only matters for
    # a point exactly on a shared edge.
    location_point = Point(lon, lat)
    for feature in reversed(ZONING_LAYER_CACHE):
        try:
            if not feature["geometry"].intersects(location_point):
                continue
        except Exception:
            continue
        score, status = zoning_class_score(feature["zone_class"], business_key)
        return score, status, feature["zone_class"]

    return 0, OUTSIDE_ZONES_STATUS, None
