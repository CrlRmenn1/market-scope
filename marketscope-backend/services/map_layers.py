"""Admin map layers: hazard and zoning polygons stored in the database.

How it fits together
  - An admin draws, traces or imports polygons (routers/map_layers.py). Every
    save goes through normalize_layer_geojson(): only polygons are kept, broken
    shapes are repaired, each polygon needs a valid zone_class, and everything
    is clipped to PANABO_BOUNDS.
  - One layer per category can be active. services/hazard.py and
    services/zoning.py score against the active layer and keep it in memory;
    changing the active layer reloads those caches and marks saved trend scans
    stale (get_map_layers_changed_at).
  - On first startup seed_builtin_map_layers() copies the old flood file and
    zoning boxes into the database as active "built-in" layers, so scores are
    unchanged until an admin activates something else.
"""
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from constants.geo import PANABO_BOUNDS
from constants.map_layers import (
    DEFAULT_IMPORT_CLASS,
    HAZARD_VAR_CLASSES,
    MAP_LAYER_CATEGORIES,
    ZONE_CLASSES_BY_CATEGORY,
    builtin_zoning_feature_collection,
)
from core.paths import BACKEND_DIR
from db.map_layer_queries import (
    delete_layer,
    get_active_layer,
    get_flag,
    get_layer,
    get_layer_file,
    insert_layer,
    insert_layer_file,
    list_layers,
    open_map_layer_cursor,
    set_flag,
    set_layer_active,
    update_layer,
)
from services import hazard as hazard_service
from services import zoning as zoning_service
from utils.geo_libs import box, gpd, make_valid, mapping, shape, unary_union


MAX_IMPORT_BYTES = 20 * 1024 * 1024
MAX_NAME_LENGTH = 255
MAX_LABEL_LENGTH = 120
IMPORT_EXTENSIONS = (".geojson", ".json", ".zip", ".kml")
IMPORT_CONTENT_TYPES = {
    ".geojson": "application/geo+json",
    ".json": "application/json",
    ".zip": "application/zip",
    ".kml": "application/vnd.google-earth.kml+xml",
}

SEED_FLAG = "map_layers_seeded"
CHANGED_FLAG = "map_layers_changed_at"

# Where the built-in flood layer was read from before layers moved into the database.
BUILTIN_HAZARD_SOURCES = [
    BACKEND_DIR / "data" / "flood" / "panabo_hazard_5yr.geojson",
    BACKEND_DIR / "panabo_hazard_5yr.geojson",
    BACKEND_DIR / "data" / "fallback" / "DavaoDelNorte" / "DavaoDelNorte_Flood_5year.shp",
    BACKEND_DIR / "data" / "fallback" / "Davao_del_Norte.geojson",
]


class MapLayerError(ValueError):
    """Bad input from the admin (shown as a 400)."""


class MapLayerNotFound(LookupError):
    pass


def _log(message: str):
    print(f"[map-layers] {message}", flush=True)


# ---- cleaning polygons --------------------------------------------------------

def _panabo_clip():
    return box(PANABO_BOUNDS[2], PANABO_BOUNDS[0], PANABO_BOUNDS[3], PANABO_BOUNDS[1])


def _polygonal(geometry):
    """Keep only the polygon parts of a geometry (drops stray lines/points)."""
    if geometry is None or geometry.is_empty:
        return None
    if geometry.geom_type in ("Polygon", "MultiPolygon"):
        return geometry
    if geometry.geom_type == "GeometryCollection":
        parts = [part for part in geometry.geoms if part.geom_type in ("Polygon", "MultiPolygon") and not part.is_empty]
        if parts:
            return unary_union(parts)
    return None


def _clean_geometry(raw_geometry, clip):
    try:
        geometry = shape(raw_geometry)
    except Exception:
        return None
    if not geometry.is_valid:
        geometry = make_valid(geometry)
    geometry = _polygonal(geometry)
    if geometry is None:
        return None
    return _polygonal(geometry.intersection(clip))


def _raw_features(geojson):
    if not isinstance(geojson, dict):
        raise MapLayerError("Layer data must be a GeoJSON object.")
    if geojson.get("type") == "FeatureCollection":
        return [feature for feature in geojson.get("features") or [] if isinstance(feature, dict)]
    if geojson.get("type") == "Feature":
        return [geojson]
    if geojson.get("type") in ("Polygon", "MultiPolygon"):
        return [{"type": "Feature", "properties": {}, "geometry": geojson}]
    raise MapLayerError("Layer data must be a GeoJSON FeatureCollection, Feature or Polygon.")


def resolve_zone_class(category: str, properties: dict, default: str | None = None):
    """properties.zone_class when valid; for hazard layers a flood Var column also works."""
    properties = properties or {}
    zone_class = str(properties.get("zone_class") or "").strip().lower()
    if zone_class in ZONE_CLASSES_BY_CATEGORY[category]:
        return zone_class

    if category == "hazard":
        var_key = next((key for key in properties if str(key).strip().lower() == "var"), None)
        if var_key is not None:
            try:
                zone_class = HAZARD_VAR_CLASSES.get(int(float(properties[var_key])))
            except (TypeError, ValueError):
                zone_class = None
            if zone_class:
                return zone_class

    return default


def normalize_layer_geojson(category: str, geojson, default_class: str | None = None):
    """Clean a layer into a FeatureCollection of clipped polygons with zone_class (and optional label)."""
    if shape is None:
        raise MapLayerError("Geometry support (shapely) is not installed on the server.")

    clip = _panabo_clip()
    features = []
    for index, feature in enumerate(_raw_features(geojson), start=1):
        properties = feature.get("properties") or {}
        zone_class = resolve_zone_class(category, properties, default_class)
        if zone_class is None:
            raise MapLayerError(f"Polygon {index} has no valid zone class for a {category} layer.")

        geometry = _clean_geometry(feature.get("geometry"), clip)
        if geometry is None:
            continue

        clean_properties = {"zone_class": zone_class}
        label = str(properties.get("label") or "").strip()[:MAX_LABEL_LENGTH]
        if label:
            clean_properties["label"] = label
        features.append({"type": "Feature", "properties": clean_properties, "geometry": mapping(geometry)})

    if not features:
        raise MapLayerError("The layer has no polygons inside the Panabo main area.")

    return {"type": "FeatureCollection", "features": features}


# ---- reading GIS files ----------------------------------------------------------

def _find_dataset(folder: Path):
    for pattern in ("*.shp", "*.geojson", "*.json", "*.kml"):
        found = sorted(folder.rglob(pattern))
        if found:
            return found[0]
    return None


def _read_gis_file(filename: str, data: bytes):
    suffix = Path(filename).suffix.lower()
    if gpd is None:
        raise MapLayerError("GIS file support (geopandas) is not installed on the server.")

    with TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        upload_path = tmp_dir / f"upload{suffix}"
        upload_path.write_bytes(data)

        dataset_path = upload_path
        if suffix == ".zip":
            extract_dir = tmp_dir / "unzipped"
            try:
                with zipfile.ZipFile(upload_path) as archive:
                    archive.extractall(extract_dir)
            except zipfile.BadZipFile:
                raise MapLayerError("The .zip file could not be opened.")
            dataset_path = _find_dataset(extract_dir)
            if dataset_path is None:
                raise MapLayerError("The .zip file has no shapefile (.shp), GeoJSON or KML inside.")

        try:
            gdf = gpd.read_file(dataset_path)
        except Exception as exc:
            raise MapLayerError(f"The file could not be read as map data: {exc}")

    if gdf.empty:
        raise MapLayerError("The file has no shapes in it.")
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def _label_column(gdf):
    for candidate in ("label", "name", "zone", "zone_name", "description"):
        found = next((col for col in gdf.columns if str(col).strip().lower() == candidate), None)
        if found:
            return found
    return None


def gis_file_to_feature_collection(category: str, filename: str, data: bytes):
    """Read an uploaded GeoJSON / zipped shapefile / KML into a cleaned layer FeatureCollection."""
    gdf = _read_gis_file(filename, data)
    label_column = _label_column(gdf)
    raw_features = []
    for _, row in gdf.iterrows():
        if row.geometry is None or row.geometry.is_empty:
            continue
        properties = {str(key): value for key, value in row.items() if key != "geometry"}
        properties["zone_class"] = resolve_zone_class(category, properties, DEFAULT_IMPORT_CLASS[category])
        properties["label"] = str(row[label_column]) if label_column and row[label_column] is not None else ""
        raw_features.append({"type": "Feature", "properties": properties, "geometry": mapping(row.geometry)})
    return normalize_layer_geojson(category, {"type": "FeatureCollection", "features": raw_features})


# ---- what changes when the active layer changes ------------------------------------

_CHANGED_AT = None
_CHANGED_AT_LOADED = False
_CHANGED_AT_LOCK = Lock()


def get_map_layers_changed_at():
    """When an active layer last changed. Trend scans that started earlier are stale."""
    global _CHANGED_AT, _CHANGED_AT_LOADED
    if _CHANGED_AT_LOADED:
        return _CHANGED_AT
    with _CHANGED_AT_LOCK:
        if not _CHANGED_AT_LOADED:
            try:
                with open_map_layer_cursor() as cursor:
                    flag = get_flag(cursor, CHANGED_FLAG)
                _CHANGED_AT = flag["set_at"] if flag else None
                _CHANGED_AT_LOADED = True
            except Exception as exc:
                _log(f"could not read the last layer change time: {exc}")
                return None
    return _CHANGED_AT


def _active_layer_changed(cursor, category: str):
    """Call inside the transaction that changed the active layer of a category."""
    return category, set_flag(cursor, CHANGED_FLAG)


def _apply_active_layer_change(change):
    """Call after that transaction committed."""
    global _CHANGED_AT, _CHANGED_AT_LOADED
    if not change:
        return
    category, changed_at = change
    with _CHANGED_AT_LOCK:
        _CHANGED_AT = changed_at
        _CHANGED_AT_LOADED = True
    if category == "hazard":
        hazard_service.reload_hazard_layer_cache()
    else:
        zoning_service.reload_zoning_layer_cache()
    _log(f"active {category} layer changed; caches reloaded and saved trend scans marked stale")


def map_layers_replaced():
    """Call after a backup upload replaced the map layer tables (services/data_backup.py)."""
    with open_map_layer_cursor() as cursor:
        changed_at = set_flag(cursor, CHANGED_FLAG)
    for category in MAP_LAYER_CATEGORIES:
        _apply_active_layer_change((category, changed_at))


# ---- admin operations --------------------------------------------------------------

def _check_category(category: str):
    category = str(category or "").strip().lower()
    if category not in MAP_LAYER_CATEGORIES:
        raise MapLayerError("Category must be 'hazard' or 'zoning'.")
    return category


def _check_name(name: str):
    name = str(name or "").strip()
    if not name:
        raise MapLayerError("Layer name is required.")
    return name[:MAX_NAME_LENGTH]


def _clean_note(source_note):
    note = str(source_note or "").strip()
    return note or None


def list_map_layers(category: str | None = None):
    if category:
        category = _check_category(category)
    with open_map_layer_cursor() as cursor:
        return list_layers(cursor, category)


def get_map_layer(layer_id: int):
    with open_map_layer_cursor() as cursor:
        layer = get_layer(cursor, layer_id)
    if not layer:
        raise MapLayerNotFound()
    return layer


def get_active_map_layer(category: str):
    category = _check_category(category)
    with open_map_layer_cursor() as cursor:
        return get_active_layer(cursor, category)


def create_map_layer(category: str, name: str, source_note: str | None, geojson, activate: bool = False):
    category = _check_category(category)
    name = _check_name(name)
    clean_geojson = normalize_layer_geojson(category, geojson)

    change = None
    with open_map_layer_cursor() as cursor:
        layer_id = insert_layer(cursor, category, name, _clean_note(source_note), "drawn", clean_geojson, is_active=activate)
        if activate:
            change = _active_layer_changed(cursor, category)
        layer = get_layer(cursor, layer_id)
    _apply_active_layer_change(change)
    return layer


def import_map_layer(category: str, name: str, source_note: str | None, filename: str, content_type: str | None, data: bytes):
    """Create an inactive layer from a GIS file and keep the original file with it."""
    category = _check_category(category)
    name = _check_name(name or Path(filename or "").stem)
    filename = Path(filename or "").name or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in IMPORT_EXTENSIONS:
        raise MapLayerError("Supported files: .geojson, .json, .kml, or a .zip containing a shapefile.")
    if not data:
        raise MapLayerError("The file is empty.")
    if len(data) > MAX_IMPORT_BYTES:
        raise MapLayerError(f"The file is larger than {MAX_IMPORT_BYTES // (1024 * 1024)} MB.")

    clean_geojson = gis_file_to_feature_collection(category, filename, data)

    with open_map_layer_cursor() as cursor:
        layer_id = insert_layer(cursor, category, name, _clean_note(source_note), "imported", clean_geojson)
        insert_layer_file(cursor, layer_id, filename, content_type or IMPORT_CONTENT_TYPES.get(suffix), data)
        return get_layer(cursor, layer_id)


def update_map_layer(layer_id: int, name: str, source_note: str | None, geojson):
    name = _check_name(name)
    change = None
    with open_map_layer_cursor() as cursor:
        existing = get_layer(cursor, layer_id)
        if not existing:
            raise MapLayerNotFound()
        clean_geojson = normalize_layer_geojson(existing["category"], geojson)
        update_layer(cursor, layer_id, name, _clean_note(source_note), clean_geojson)
        if existing["is_active"]:
            change = _active_layer_changed(cursor, existing["category"])
        layer = get_layer(cursor, layer_id)
    _apply_active_layer_change(change)
    return layer


def set_map_layer_active(layer_id: int, is_active: bool):
    with open_map_layer_cursor() as cursor:
        existing = set_layer_active(cursor, layer_id, is_active)
        if not existing:
            raise MapLayerNotFound()
        change = _active_layer_changed(cursor, existing["category"])
        layer = get_layer(cursor, layer_id)
    _apply_active_layer_change(change)
    return layer


def delete_map_layer(layer_id: int):
    change = None
    with open_map_layer_cursor() as cursor:
        deleted = delete_layer(cursor, layer_id)
        if not deleted:
            raise MapLayerNotFound()
        if deleted["is_active"]:
            change = _active_layer_changed(cursor, deleted["category"])
    _apply_active_layer_change(change)
    return deleted["id"]


def get_map_layer_file(layer_id: int, file_id: int):
    with open_map_layer_cursor() as cursor:
        found = get_layer_file(cursor, layer_id, file_id)
    if not found:
        raise MapLayerNotFound()
    return found


# ---- one-time seed of the built-in layers ----------------------------------------------

def _load_builtin_hazard_layer():
    for path in BUILTIN_HAZARD_SOURCES:
        if not path.exists():
            continue
        try:
            gdf = _read_gis_file(path.name, path.read_bytes())
            raw_features = []
            for _, row in gdf.iterrows():
                if row.geometry is None or row.geometry.is_empty:
                    continue
                properties = {str(key): value for key, value in row.items() if key != "geometry"}
                zone_class = resolve_zone_class("hazard", properties)
                if zone_class is None:
                    continue
                raw_features.append({"type": "Feature", "properties": {"zone_class": zone_class}, "geometry": mapping(row.geometry)})
            return normalize_layer_geojson("hazard", {"type": "FeatureCollection", "features": raw_features}), path
        except MapLayerError as exc:
            _log(f"built-in flood source skipped ({path}): {exc}")
    return None, None


def seed_builtin_map_layers():
    """First startup only: copy the old flood file and zoning boxes into the database as active layers."""
    try:
        with open_map_layer_cursor() as cursor:
            if get_flag(cursor, SEED_FLAG):
                return

            hazard_geojson, hazard_path = _load_builtin_hazard_layer()
            if hazard_geojson:
                layer_id = insert_layer(
                    cursor, "hazard", "Built-in: NOAH 5-year flood (Panabo)",
                    "Davao del Norte 5-year return period flood hazard (NOAH/DENR), clipped to Panabo.",
                    "builtin", hazard_geojson, is_active=True,
                )
                suffix = hazard_path.suffix.lower()
                if suffix in (".geojson", ".json"):
                    insert_layer_file(cursor, layer_id, hazard_path.name, IMPORT_CONTENT_TYPES[suffix], hazard_path.read_bytes())
            else:
                _log("no built-in flood file found; no hazard layer seeded")

            insert_layer(
                cursor, "zoning", "Built-in: default zoning areas",
                "The commercial center and agri-industrial boxes the system used before zoning layers.",
                "builtin", builtin_zoning_feature_collection(), is_active=True,
            )
            set_flag(cursor, SEED_FLAG, "1")
        _log("seeded the built-in hazard and zoning layers")
    except Exception as exc:
        _log(f"seeding built-in layers failed (will retry next startup): {exc}")
