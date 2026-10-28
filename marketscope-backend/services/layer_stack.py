"""Stacking rule for map layers: the shape on top wins its area.

A layer's geojson.features array is a stack: the first feature is at the
bottom, the last is on top. Shapes are stored whole; anything that scores or
displays a layer flattens the stack first, so each shape keeps only the part
not covered by shapes above it and no two flattened shapes overlap.

Kept separate from services/map_layers.py so services/hazard.py and
services/zoning.py can use it without a circular import.
"""
from constants.map_layers import HAZARD_CLASS_VARS, LEGACY_ZONING_SCORES
from utils.geo_libs import make_valid, mapping, shape, unary_union


def polygonal(geometry):
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


def _feature_geometry(feature):
    try:
        geometry = shape(feature["geometry"])
    except Exception:
        return None
    if not geometry.is_valid:
        geometry = make_valid(geometry)
    return polygonal(geometry)


def flatten_features(features):
    """[{zone_class, label, geometry}] with each shape minus every shape above it.

    Order is kept (bottom to top); shapes left with no visible area are dropped.
    """
    stack = []
    for feature in features or []:
        properties = feature.get("properties") or {}
        geometry = _feature_geometry(feature)
        if geometry is not None:
            stack.append({"zone_class": properties.get("zone_class"), "label": properties.get("label"), "geometry": geometry})

    flattened = []
    covered = None
    for item in reversed(stack):
        geometry = item["geometry"]
        visible = geometry if covered is None else polygonal(geometry.difference(covered))
        covered = geometry if covered is None else covered.union(geometry)
        if visible is not None and not visible.is_empty:
            flattened.append({**item, "geometry": visible})
    flattened.reverse()
    return flattened


def flatten_feature_collection(geojson):
    """The flattened stack as a GeoJSON FeatureCollection (for the user maps)."""
    features = []
    for item in flatten_features((geojson or {}).get("features")):
        properties = {"zone_class": item["zone_class"]}
        if item.get("label"):
            properties["label"] = item["label"]
        features.append({"type": "Feature", "properties": properties, "geometry": mapping(item["geometry"])})
    return {"type": "FeatureCollection", "features": features}


def _old_priority(category, feature):
    zone_class = (feature.get("properties") or {}).get("zone_class")
    if category == "hazard":
        # Var 1 = Very High ... 3 = Moderate; the most severe goes on top.
        return -HAZARD_CLASS_VARS.get(zone_class, 99)
    # Only the pre-LGU zoning classes had scores; LGU zones keep their order.
    return LEGACY_ZONING_SCORES.get(zone_class, 0)


def order_by_old_priority(category, features):
    """Stack order that reproduces the rule used before stacking.

    Hazard: Moderate, High, Very High (most severe on top).
    Zoning: lowest old score first, so the best-scoring old class is on top
    (LGU zones have no ranking and keep their order).
    Used for layers saved before stacking and for imported GIS files, whose
    row order means nothing. The sort is stable.
    """
    return sorted(features or [], key=lambda feature: _old_priority(category, feature))
