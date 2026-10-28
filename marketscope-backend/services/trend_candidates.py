"""Where the background trend scan looks: the list of candidate spots.

Three kinds of candidates, in priority order (when two land on the same spot,
the first one wins):
  1. "space"    - every active For Rent / For Sale listing (an actual available space)
  2. "landmark" - the Panabo anchor landmarks (market, terminal, schools...)
  3. "area"     - a grid of points (~330 m apart) inside the active zoning layer's
                  polygons of every LGU zone the business type is allowed in
                  (the admin's allowed-uses table, services/zoning.py).
"""
from constants.geo import PANABO_ANCHORS
from constants.map_layers import ZONING_CLASSES
from services.zoning import allowed_zone_classes, get_zoning_features
from utils.geo_libs import Point
from utils.values import to_finite_number


GRID_STEP_DEGREES = 0.003  # about 330 m in Panabo


def build_area_grid_points(zone_feature, step: float = GRID_STEP_DEGREES):
    """Grid points inside one zoning polygon ({"zone_class", "label", "geometry"})."""
    geometry = zone_feature["geometry"]
    min_lon, min_lat, max_lon, max_lat = geometry.bounds
    lat_count = int((max_lat - min_lat) / step + 1e-9) + 1
    lon_count = int((max_lon - min_lon) / step + 1e-9) + 1
    zone_label = zone_feature.get("label") or ZONING_CLASSES[zone_feature["zone_class"]]["label"]

    points = []
    for lat_index in range(lat_count):
        for lon_index in range(lon_count):
            lat = round(min_lat + lat_index * step, 6)
            lon = round(min_lon + lon_index * step, 6)
            if not geometry.covers(Point(lon, lat)):
                continue
            points.append({
                "lat": lat,
                "lon": lon,
                "label": f"{zone_label} spot {len(points) + 1}",
                "source": "area",
                "space_id": None,
            })
    return points


def build_scan_candidates(business_key: str, space_markers=None, zoning_features=None, allowed_zones=None):
    """zoning_features defaults to the active zoning layer and allowed_zones to the
    zones this business type is allowed in (both from services/zoning.py)."""
    candidates = []

    for marker in space_markers or []:
        lat = to_finite_number(marker.get("latitude"))
        lon = to_finite_number(marker.get("longitude"))
        if lat is None or lon is None:
            continue
        candidates.append({
            "lat": lat,
            "lon": lon,
            "label": marker.get("title") or "Listed space",
            "source": "space",
            "space_id": str(marker.get("id")) if marker.get("id") is not None else None,
        })

    for anchor in PANABO_ANCHORS:
        candidates.append({
            "lat": anchor["lat"],
            "lon": anchor["lon"],
            "label": f"Near {anchor['name']}",
            "source": "landmark",
            "space_id": None,
        })

    if zoning_features is None:
        zoning_features = get_zoning_features()
    allowed_classes = allowed_zone_classes(business_key) if allowed_zones is None else set(allowed_zones)
    for zone_feature in zoning_features:
        if zone_feature["zone_class"] in allowed_classes:
            candidates.extend(build_area_grid_points(zone_feature))

    # Drop spots within ~10 m of one already in the list.
    deduped = []
    seen = set()
    for candidate in candidates:
        key = (round(candidate["lat"], 4), round(candidate["lon"], 4))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)

    return deduped
