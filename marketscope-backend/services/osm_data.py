"""OpenStreetMap (panabo.pbf) caches: competitors, anchors, roads, buildings, and the reference road map.

GDAL only gives some OSM tags their own column; the rest stay in "other_tags". On
the points layer that includes amenity and shop, so reading only the columns would
miss almost every shop mapped as a point. _feature_tags() reads both.
"""
import json
import re
import time
import warnings
from threading import Lock

from constants.engine import (
    OSM_ANCHOR_TAGS,
    OSM_BARANGAY_HALL_POWER,
    ROAD_CLASS_VALUES,
    ROAD_IGNORED_CLASSES,
    TREND_AREA_PLACE_TYPES,
)
from constants.geo import PANABO_BOUNDS
from constants.msme import (
    COMMERCIAL_AMENITY_VALUES,
    PBF_NAME_KEYWORD_FALLBACK,
)
from core.paths import PBF_PATH
from utils.geo import calculate_distance, check_inside_bounds, local_xy
from utils.geo_libs import STRtree, box, gpd, mapping, np, shapely_lib
from utils.values import normalize_osm_value


# (tag_key, tag_value) -> [features]
PBF_COMPETITOR_CACHE = {}


PBF_ALL_COMPETITORS = []


# [{"osm_ref", "name", "category", "power", "lat", "lon", "tag"}]
PBF_ANCHOR_FEATURES = []


# Named places that give trend areas their names: [{"name", "place", "lat", "lon"}]
PBF_PLACE_FEATURES = []


PBF_CACHE_LOADED = False


# False when the file is missing or couldn't be read: the scan reports it instead
# of treating "no data" as "no competitors".
PBF_FEATURES_AVAILABLE = False


PBF_CACHE_LOCK = Lock()


PBF_FEATURE_LAYERS = ["points", "multipolygons"]


PBF_COLUMN_TAGS = ["amenity", "shop", "healthcare", "leisure", "office", "public_transport", "place"]


PBF_COMPETITOR_KEYS = ["amenity", "shop", "healthcare"]


OTHER_TAGS_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')


ROAD_INDEX = None


BUILDING_INDEX = None


PBF_SPATIAL_CONTEXT_LOADED = False


PBF_SPATIAL_CONTEXT_LOCK = Lock()


# A failed read is retried, but not on every scan.
LOAD_RETRY_SECONDS = 60
_LAST_FEATURE_FAILURE = None
_LAST_SPATIAL_FAILURE = None


def _retry_too_soon(failed_at):
    return failed_at is not None and time.monotonic() - failed_at < LOAD_RETRY_SECONDS


def _clean_name(value):
    if isinstance(value, str):
        return value.strip() or None
    return None


def _normalize_road_class(value):
    normalized = normalize_osm_value(value)
    if normalized is None:
        return None

    normalized = normalized.replace("-", "_")
    normalized = normalized.replace(" ", "_")
    normalized = normalized.replace("__", "_")

    if normalized.endswith("_link"):
        normalized = normalized[:-5]

    if normalized in ROAD_CLASS_VALUES or normalized in ROAD_IGNORED_CLASSES:
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


def _to_local_geometries(geometries):
    """Geometries from lon/lat degrees to Panabo-local metres, so distances are real metres."""
    def transform(coords):
        x, y = local_xy(coords[:, 1], coords[:, 0])
        return np.column_stack([x, y])

    return shapely_lib.transform(np.asarray(geometries), transform)


class RoadIndex:
    """Road lines in local metres, searchable by distance."""

    def __init__(self, lon_lat_geometries, road_classes, names):
        self.geometries = _to_local_geometries(lon_lat_geometries)
        self.road_classes = list(road_classes)
        self.names = [_clean_name(name) for name in names]
        self.tree = STRtree(self.geometries)

    def __len__(self):
        return len(self.road_classes)

    def nearest_by_class(self, lat, lon, max_distance_m):
        """{road class: (distance_m, name)} for the closest road of each class in range."""
        x, y = local_xy(lat, lon)
        origin = shapely_lib.points(float(x), float(y))
        found = np.sort(self.tree.query(origin, predicate="dwithin", distance=max_distance_m))
        if len(found) == 0:
            return {}

        distances = shapely_lib.distance(self.geometries[found], origin)
        nearest = {}
        for index, distance_m in zip(found, distances):
            road_class = self.road_classes[index]
            if road_class not in nearest or distance_m < nearest[road_class][0]:
                nearest[road_class] = (float(distance_m), self.names[index])
        return nearest


class BuildingIndex:
    """Built features as arrays of local-metre points, summed by distance."""

    def __init__(self, xs, ys, feature_weights, area_bonuses):
        self.xs = np.asarray(xs, dtype=float)
        self.ys = np.asarray(ys, dtype=float)
        self.values = np.asarray(feature_weights, dtype=float) * np.asarray(area_bonuses, dtype=float)

    def __len__(self):
        return len(self.xs)

    def intensity(self, lat, lon, reach_m):
        """(sum of value * linear fade to reach_m, features in reach)."""
        x, y = local_xy(lat, lon)
        distances = np.hypot(self.xs - float(x), self.ys - float(y))
        in_reach = distances < reach_m
        fade = 1.0 - distances[in_reach] / reach_m
        return float(np.sum(self.values[in_reach] * fade)), int(np.count_nonzero(in_reach))


def _building_area_bonus(area_m2):
    return 1.0 + np.minimum(2.0, area_m2 / 2500.0) * 0.18


def _build_road_index(road_gdf):
    if road_gdf is None or road_gdf.empty or "highway" not in road_gdf.columns:
        return None

    road_gdf = road_gdf[road_gdf["geometry"].notna() & road_gdf["highway"].notna()].copy()
    road_gdf["road_class"] = road_gdf["highway"].apply(_normalize_road_class)
    road_gdf = road_gdf[road_gdf["road_class"].isin(ROAD_CLASS_VALUES.keys())]
    if road_gdf.empty:
        return None

    names = road_gdf["name"] if "name" in road_gdf.columns else [None] * len(road_gdf)
    return RoadIndex(road_gdf.geometry.values, road_gdf["road_class"], names)


def _build_building_index(building_gdf):
    if building_gdf is None or building_gdf.empty:
        return None

    columns = [col for col in ["building", "landuse", "amenity", "shop", "office"] if col in building_gdf.columns]
    if not columns:
        return None

    mask = building_gdf[columns].notna().any(axis=1) & building_gdf["geometry"].notna()
    building_gdf = building_gdf.loc[mask, columns + ["geometry"]]
    if building_gdf.empty:
        return None

    weights = building_gdf.apply(_feature_weight_from_building_row, axis=1).to_numpy()
    local_geometries = _to_local_geometries(building_gdf.geometry.values)
    centroids = shapely_lib.centroid(local_geometries)
    return BuildingIndex(
        shapely_lib.get_x(centroids),
        shapely_lib.get_y(centroids),
        weights,
        _building_area_bonus(shapely_lib.area(local_geometries)),
    )


def preload_pbf_spatial_context_cache():
    global ROAD_INDEX, BUILDING_INDEX, PBF_SPATIAL_CONTEXT_LOADED, _LAST_SPATIAL_FAILURE

    if PBF_SPATIAL_CONTEXT_LOADED or _retry_too_soon(_LAST_SPATIAL_FAILURE):
        return

    with PBF_SPATIAL_CONTEXT_LOCK:
        if PBF_SPATIAL_CONTEXT_LOADED or _retry_too_soon(_LAST_SPATIAL_FAILURE):
            return

        if gpd is None or STRtree is None:
            PBF_SPATIAL_CONTEXT_LOADED = True
            print("PBF spatial context cache skipped: geopandas/shapely unavailable")
            return

        if not PBF_PATH.exists():
            PBF_SPATIAL_CONTEXT_LOADED = True
            print(f"PBF spatial context cache skipped: file not found at {PBF_PATH}")
            return

        try:
            road_index = _build_road_index(gpd.read_file(str(PBF_PATH), layer="lines", engine="pyogrio"))
            building_index = _build_building_index(gpd.read_file(str(PBF_PATH), layer="multipolygons", engine="pyogrio"))
        except Exception as exc:
            _LAST_SPATIAL_FAILURE = time.monotonic()
            print(f"PBF spatial context read failed; will retry: {exc}")
            return

        ROAD_INDEX = road_index
        BUILDING_INDEX = building_index
        _LAST_SPATIAL_FAILURE = None
        PBF_SPATIAL_CONTEXT_LOADED = True
        print(
            "PBF spatial context loaded: "
            f"roads={0 if ROAD_INDEX is None else len(ROAD_INDEX)}, "
            f"buildings={0 if BUILDING_INDEX is None else len(BUILDING_INDEX)}"
        )


def _feature_tags(row):
    """All the OSM tags of a layer row: its own columns plus the other_tags text."""
    tags = {}
    other_tags = row.get("other_tags")
    if isinstance(other_tags, str):
        tags.update(OTHER_TAGS_PATTERN.findall(other_tags))
    for column in PBF_COLUMN_TAGS:
        value = row.get(column)
        if isinstance(value, str) and value:
            tags[column] = value
    return tags


def _osm_ref(row):
    way_id = row.get("osm_way_id")
    if isinstance(way_id, str) and way_id:
        return f"way/{way_id}"
    osm_id = row.get("osm_id")
    if isinstance(osm_id, str) and osm_id:
        # multipolygons with no way id are OSM relations; everything else here is a node.
        return f"relation/{osm_id}" if row.get("__layer") == "multipolygons" else f"node/{osm_id}"
    return None


def anchor_tag_for(tags, name):
    """(category, power, "key=value") when these tags make a place an anchor, else None."""
    for (key, value), (category, power) in OSM_ANCHOR_TAGS.items():
        if normalize_osm_value(tags.get(key)) != value:
            continue
        if value == "townhall" and "barangay" in (name or "").lower():
            power = OSM_BARANGAY_HALL_POWER
        return category, power, f"{key}={value}"
    return None


def _dedupe_anchor_features(features, within_m=150.0):
    """The same named place is often mapped twice, as a point and as a building."""
    kept = []
    for feature in features:
        duplicate = any(
            other["name"].lower() == feature["name"].lower()
            and calculate_distance(other["lat"], other["lon"], feature["lat"], feature["lon"]) <= within_m
            for other in kept
        )
        if not duplicate:
            kept.append(feature)
    return kept


def _read_tagged_features():
    """Yield (row, tags, lat, lon) for every point/polygon carrying a useful tag."""
    useful_keys = set(PBF_COLUMN_TAGS)
    for layer in PBF_FEATURE_LAYERS:
        gdf = gpd.read_file(str(PBF_PATH), layer=layer, engine="pyogrio")
        for row in gdf.to_dict("records"):
            row["__layer"] = layer
            tags = _feature_tags(row)
            if not useful_keys.intersection(tags):
                continue
            geometry = row.get("geometry")
            if geometry is None or geometry.is_empty:
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                centroid = geometry.centroid
            yield row, tags, centroid.y, centroid.x


def preload_pbf_competitor_cache():
    """Loads competitors, anchors and named places, which come from the same two layers."""
    global PBF_COMPETITOR_CACHE, PBF_ALL_COMPETITORS, PBF_ANCHOR_FEATURES, PBF_PLACE_FEATURES
    global PBF_CACHE_LOADED, PBF_FEATURES_AVAILABLE, _LAST_FEATURE_FAILURE

    if PBF_CACHE_LOADED or _retry_too_soon(_LAST_FEATURE_FAILURE):
        return

    with PBF_CACHE_LOCK:
        if PBF_CACHE_LOADED or _retry_too_soon(_LAST_FEATURE_FAILURE):
            return

        if gpd is None:
            PBF_CACHE_LOADED = True
            print("PBF cache skipped: geopandas is unavailable")
            return

        if not PBF_PATH.exists():
            PBF_CACHE_LOADED = True
            print(f"PBF cache skipped: file not found at {PBF_PATH}")
            return

        cache = {}
        all_competitors = []
        anchors = []
        places = []

        try:
            for row, tags, lat, lon in _read_tagged_features():
                name = _clean_name(row.get("name"))
                osm_ref = _osm_ref(row)

                for key in PBF_COMPETITOR_KEYS:
                    value = normalize_osm_value(tags.get(key))
                    if not value:
                        continue
                    entry = {"lat": lat, "lon": lon, "name": name, "tag_key": key, "tag_value": value, "osm_ref": osm_ref}
                    cache.setdefault((key, value), []).append(entry)
                    all_competitors.append(entry)

                anchor_tag = anchor_tag_for(tags, name)
                if anchor_tag and name and osm_ref:
                    category, power, tag = anchor_tag
                    anchors.append({
                        "osm_ref": osm_ref,
                        "name": name,
                        "category": category,
                        "power": power,
                        "lat": lat,
                        "lon": lon,
                        "tag": tag,
                    })

                place_type = normalize_osm_value(tags.get("place"))
                if name and place_type in TREND_AREA_PLACE_TYPES and check_inside_bounds(lat, lon, PANABO_BOUNDS):
                    places.append({"name": name, "place": place_type, "lat": lat, "lon": lon})
        except Exception as exc:
            _LAST_FEATURE_FAILURE = time.monotonic()
            print(f"PBF feature read failed; will retry: {exc}")
            return

        PBF_COMPETITOR_CACHE = cache
        PBF_ALL_COMPETITORS = all_competitors
        PBF_ANCHOR_FEATURES = _dedupe_anchor_features(anchors)
        PBF_PLACE_FEATURES = _dedupe_anchor_features(places)
        PBF_FEATURES_AVAILABLE = True
        _LAST_FEATURE_FAILURE = None
        PBF_CACHE_LOADED = True
        print(
            f"PBF cache loaded: {len(all_competitors)} tagged features for {len(cache)} tags, "
            f"{len(PBF_ANCHOR_FEATURES)} anchors, {len(PBF_PLACE_FEATURES)} named places"
        )


def get_cached_pbf_competitors(tag_key, tag_value):
    preload_pbf_competitor_cache()
    return PBF_COMPETITOR_CACHE.get((normalize_osm_value(tag_key), normalize_osm_value(tag_value)), [])


def get_osm_anchor_features():
    preload_pbf_competitor_cache()
    return PBF_ANCHOR_FEATURES


def get_osm_place_features():
    preload_pbf_competitor_cache()
    return PBF_PLACE_FEATURES


def _keyword_pattern(keywords):
    # Whole words only: "wash" must not make a car wash a laundry competitor.
    return re.compile(r"\b(?:" + "|".join(re.escape(keyword) for keyword in keywords) + r")\b", re.IGNORECASE)


_KEYWORD_PATTERNS = {key: _keyword_pattern(words) for key, words in PBF_NAME_KEYWORD_FALLBACK.items() if words}


def get_name_keyword_pbf_competitors(business_type):
    """Businesses whose name says what they are, even when OSM has no matching tag."""
    preload_pbf_competitor_cache()

    pattern = _KEYWORD_PATTERNS.get(normalize_osm_value(business_type) or "")
    if pattern is None:
        return []

    matches = []
    for item in PBF_ALL_COMPETITORS:
        # Schools, churches and the like can have any word in their name.
        if item["tag_key"] == "amenity" and item["tag_value"] not in COMMERCIAL_AMENITY_VALUES:
            continue
        if item["name"] and pattern.search(item["name"]):
            matches.append(item)
    return matches


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
