"""Where the background trend scan looks: the list of candidate spots.

Three kinds of candidates, in priority order (when two land on the same spot,
the first one wins):
  1. "space"    - every active For Rent / For Sale listing (an actual available space)
  2. "landmark" - the Panabo anchor landmarks (market, terminal, schools...)
  3. "area"     - a grid of points (~330 m apart) over the zoning boxes the
                  business is allowed in: always the commercial center, plus the
                  agri-industrial zone for INDUSTRIAL_ZONE_BUSINESSES.
"""
from constants.geo import INDUSTRIAL_ZONE_BUSINESSES, PANABO_ANCHORS, ZONING_LAYERS
from utils.values import to_finite_number


GRID_STEP_DEGREES = 0.003  # about 330 m in Panabo

SCAN_ZONES = {
    "commercial_proper": "Commercial center",
    "industrial_anflo": "Agri-industrial zone",
}


def _zones_for_business(business_key: str):
    zones = ["commercial_proper"]
    if business_key in INDUSTRIAL_ZONE_BUSINESSES:
        zones.append("industrial_anflo")
    return zones


def build_area_grid_points(zone_key: str, step: float = GRID_STEP_DEGREES):
    min_lat, max_lat, min_lon, max_lon = ZONING_LAYERS[zone_key]
    lat_count = int((max_lat - min_lat) / step + 1e-9) + 1
    lon_count = int((max_lon - min_lon) / step + 1e-9) + 1
    zone_label = SCAN_ZONES[zone_key]

    points = []
    for lat_index in range(lat_count):
        for lon_index in range(lon_count):
            points.append({
                "lat": round(min_lat + lat_index * step, 6),
                "lon": round(min_lon + lon_index * step, 6),
                "label": f"{zone_label} spot {len(points) + 1}",
                "source": "area",
                "space_id": None,
            })
    return points


def build_scan_candidates(business_key: str, space_markers=None):
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

    for zone_key in _zones_for_business(business_key):
        candidates.extend(build_area_grid_points(zone_key))

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
