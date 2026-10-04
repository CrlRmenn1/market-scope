"""
Flood hazard layer: loads the hazard GeoJSON/shapefile once and scores a point.

Davao del Norte 5-year flood return period hazard zones
Extracted from official NOAH/DENR flood hazard shapefile (DavaoDelNorte_Flood_5year.shp)
Intersection with Panabo City bounds (7.269-7.333 lat, 125.636-125.742 lon)
Severity levels: Var 1=Very High, Var 2=High, Var 3=Moderate
"""
from threading import Lock

from core.paths import BACKEND_DIR
from constants.geo import PANABO_BOUNDS
from utils.geo_libs import Point, box, gpd, unary_union


HAZARD_ZONES = {
    "flood": [
        {
            "name": "Very High Flood Hazard (5-Year Return Period)",
            "bounds": (7.269, 7.333, 125.636, 125.742),
            "score": 5
        },
        {
            "name": "High Flood Hazard (5-Year Return Period)",
            "bounds": (7.269, 7.333, 125.636, 125.73958735603416),
            "score": 12
        },
        {
            "name": "Moderate Flood Hazard (5-Year Return Period)",
            "bounds": (7.269, 7.333, 125.636, 125.7389400572897),
            "score": 18
        }
    ]
}


HAZARD_LAYER_CACHE = []


HAZARD_LAYER_CACHE_LOADED = False


HAZARD_LAYER_LOCK = Lock()


HAZARD_LAYER_SOURCE = None


HAZARD_LAYER_LABELS = {
    1: {"name": "Very High Flood Hazard (5-Year Return Period)", "score": 5},
    2: {"name": "High Flood Hazard (5-Year Return Period)", "score": 12},
    3: {"name": "Moderate Flood Hazard (5-Year Return Period)", "score": 18},
}


def _resolve_hazard_var(row, column_name):
    if not column_name:
        return None

    try:
        raw = row[column_name]
        if raw is None:
            return None
        return int(float(raw))
    except Exception:
        return None


def preload_hazard_layer_cache():
    global HAZARD_LAYER_CACHE, HAZARD_LAYER_CACHE_LOADED, HAZARD_LAYER_SOURCE

    if HAZARD_LAYER_CACHE_LOADED:
        return

    if gpd is None or Point is None or box is None or unary_union is None:
        HAZARD_LAYER_CACHE = []
        HAZARD_LAYER_SOURCE = None
        HAZARD_LAYER_CACHE_LOADED = True
        print("Hazard layer cache skipped: geopandas/shapely is unavailable")
        return

    with HAZARD_LAYER_LOCK:
        if HAZARD_LAYER_CACHE_LOADED:
            return

        candidates = [
            BACKEND_DIR / "data" / "flood" / "panabo_hazard_5yr.geojson",
            BACKEND_DIR / "panabo_hazard_5yr.geojson",
            BACKEND_DIR.parent / "marketscope-frontend" / "public" / "panabo_hazard_5yr.geojson",
            BACKEND_DIR / "data" / "fallback" / "DavaoDelNorte" / "DavaoDelNorte_Flood_5year.shp",
            BACKEND_DIR / "data" / "fallback" / "Davao_del_Norte.geojson",
        ]

        cache = []
        panabo_clip = box(PANABO_BOUNDS[2], PANABO_BOUNDS[0], PANABO_BOUNDS[3], PANABO_BOUNDS[1])

        for hazard_path in candidates:
            if not hazard_path.exists():
                continue

            try:
                hazard_gdf = gpd.read_file(hazard_path)
                if hazard_gdf.empty:
                    continue

                var_column = next((col for col in hazard_gdf.columns if str(col).strip().lower() == "var"), None)
                if not var_column:
                    print(f"Hazard layer skipped (missing Var field): {hazard_path}")
                    continue

                clipped = hazard_gdf.copy()
                clipped["geometry"] = clipped.geometry.intersection(panabo_clip)
                clipped = clipped[~clipped.geometry.is_empty]

                raw_geometries_by_var = {}

                for _, row in clipped.iterrows():
                    geometry = row.geometry
                    if geometry is None or geometry.is_empty:
                        continue

                    hazard_var = _resolve_hazard_var(row, var_column)
                    if hazard_var is None:
                        continue

                    label = HAZARD_LAYER_LABELS.get(hazard_var)
                    if label is None:
                        continue

                    raw_geometries_by_var.setdefault(hazard_var, []).append(geometry)

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

                if cache:
                    HAZARD_LAYER_SOURCE = str(hazard_path)
                    break
            except Exception as e:
                print(f"Hazard layer load warning for {hazard_path}: {e}")

        cache.sort(key=lambda item: item["score"])
        HAZARD_LAYER_CACHE = cache
        HAZARD_LAYER_CACHE_LOADED = True
        if HAZARD_LAYER_CACHE:
            print(f"Hazard layer cache loaded: {len(HAZARD_LAYER_CACHE)} polygon features from {HAZARD_LAYER_SOURCE}")
        else:
            print("Hazard layer cache loaded with 0 polygon features")


def evaluate_hazard(lat, lon):
    global HAZARD_LAYER_CACHE_LOADED

    # Recover from stale empty caches (for example if startup happened before files existed).
    if HAZARD_LAYER_CACHE_LOADED and not HAZARD_LAYER_CACHE:
        with HAZARD_LAYER_LOCK:
            if HAZARD_LAYER_CACHE_LOADED and not HAZARD_LAYER_CACHE:
                HAZARD_LAYER_CACHE_LOADED = False

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

        if hazard_matches and hazard_status not in hazard_matches:
            hazard_matches.insert(0, hazard_status)

        return hazard_score, hazard_status, hazard_matches

    # Do not fallback to temporary rectangular proxies; avoid false positives.
    return hazard_score, hazard_status, hazard_matches
