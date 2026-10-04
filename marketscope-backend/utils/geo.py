"""Distance, bounds, and area math."""
import math


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lon2 - lon1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def check_inside_bounds(lat, lon, bounds):
    min_lat, max_lat, min_lon, max_lon = bounds
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def _approx_polygon_area_m2(geometry):
    if geometry is None or geometry.is_empty:
        return 0.0

    try:
        area_degrees = float(getattr(geometry, "area", 0.0) or 0.0)
        centroid_lat = float(geometry.centroid.y)
        meters_per_deg_lat = 111132.92
        meters_per_deg_lon = 111412.84 * math.cos(math.radians(centroid_lat))
        return abs(area_degrees) * abs(meters_per_deg_lat) * max(1.0, abs(meters_per_deg_lon))
    except Exception:
        return 0.0
