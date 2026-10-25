"""Map layer categories and the zone classes an admin can give each polygon.

Every polygon in a map layer carries properties.zone_class. Hazard classes map
onto the flood Var levels used by services/hazard.py; zoning classes carry the
zoning score used by services/zoning.py.
"""
from constants.geo import ZONING_LAYERS


MAP_LAYER_CATEGORIES = ("hazard", "zoning")


# zone_class -> flood Var level (1 = Very High, 2 = High, 3 = Moderate).
HAZARD_CLASS_VARS = {
    "very_high": 1,
    "high": 2,
    "moderate": 3,
}


HAZARD_VAR_CLASSES = {var: zone_class for zone_class, var in HAZARD_CLASS_VARS.items()}


# Industrial gives its score to INDUSTRIAL_ZONE_BUSINESSES and other_score to everything else.
ZONING_CLASSES = {
    "commercial": {"label": "Commercial", "score": 25, "status": "Compliant (Commercial Center)"},
    "mixed_use": {"label": "Mixed-use", "score": 20, "status": "Compliant (Mixed-Use Zone)"},
    "industrial": {
        "label": "Industrial",
        "score": 25,
        "status": "Compliant (Agri-Industrial Support)",
        "other_score": 5,
        "other_status": "Non-Compliant (Heavy Industrial Zone)",
    },
    "residential": {"label": "Residential", "score": 10, "status": "Limited (Residential Zone)"},
    "institutional": {"label": "Institutional", "score": 5, "status": "Restricted (Institutional Zone)"},
    "agricultural": {"label": "Agricultural", "score": 5, "status": "Restricted (Agricultural Zone)"},
}


ZONE_CLASSES_BY_CATEGORY = {
    "hazard": tuple(HAZARD_CLASS_VARS),
    "zoning": tuple(ZONING_CLASSES),
}


# Class given to imported polygons that carry no usable class; the admin reassigns it.
DEFAULT_IMPORT_CLASS = {
    "hazard": "high",
    "zoning": "commercial",
}


# Zoning classes the trend scan places "area" candidates in.
TREND_SCAN_ZONE_CLASSES = ("commercial", "mixed_use")
TREND_SCAN_INDUSTRIAL_ZONE_CLASSES = ("industrial",)


# The zoning boxes the system used before zoning became an admin layer.
BUILTIN_ZONING_CLASSES = {
    "commercial_proper": ("commercial", "Commercial center"),
    "industrial_anflo": ("industrial", "Agri-industrial zone"),
}


def builtin_zoning_feature_collection():
    """The old ZONING_LAYERS boxes as a zoning layer FeatureCollection (used for the one-time seed)."""
    features = []
    for zone_key, (zone_class, label) in BUILTIN_ZONING_CLASSES.items():
        min_lat, max_lat, min_lon, max_lon = ZONING_LAYERS[zone_key]
        features.append({
            "type": "Feature",
            "properties": {"zone_class": zone_class, "label": label},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]],
            },
        })
    return {"type": "FeatureCollection", "features": features}
