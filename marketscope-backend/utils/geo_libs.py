"""Optional geospatial libraries.

geopandas/shapely are imported once here. If they are not installed, the
names are None and the hazard/OSM loaders skip themselves instead of crashing.
"""
try:
    import geopandas as gpd
except Exception:
    gpd = None

try:
    from shapely.geometry import Point, box, mapping, shape
    from shapely.ops import nearest_points, unary_union
    from shapely.validation import make_valid
except Exception:
    Point = None
    box = None
    mapping = None
    shape = None
    nearest_points = None
    unary_union = None
    make_valid = None
