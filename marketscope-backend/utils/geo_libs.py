"""Optional geospatial libraries.

geopandas/shapely are imported once here. If they are not installed, the
names are None and the hazard/OSM loaders skip themselves instead of crashing.
"""
try:
    import geopandas as gpd
except Exception:
    gpd = None

try:
    from shapely.geometry import Point, box
    from shapely.ops import nearest_points, unary_union
except Exception:
    Point = None
    box = None
    nearest_points = None
    unary_union = None
