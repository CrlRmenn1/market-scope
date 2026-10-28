"""Map layer categories and the zone classes an admin can give each polygon.

Every polygon in a map layer carries properties.zone_class. Hazard classes map
onto the flood Var levels used by services/hazard.py. Zoning classes are the
zones of the Panabo City Integrated Zoning Map C.Y. 2020-2029; a business is
either allowed in a zone (full zoning score) or not (zero), per the admin's
allowed-uses table (services/zoning.py).
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


# Zones of the Panabo City Integrated Zoning Map C.Y. 2020-2029, in legend
# order, with the group the admin picker shows them under.
ZONING_CLASSES = {
    "general_commercial": {"label": "General Commercial Zone", "group": "Commercial"},
    "commercial_2": {"label": "Commercial-2 (C-2) Zone", "group": "Commercial"},
    "commercial_3": {"label": "Commercial-3 (C-3) Zone", "group": "Commercial"},
    "tourism": {"label": "Tourism Zone", "group": "Commercial"},
    "general_residential": {"label": "General Residential Zone", "group": "Residential"},
    "residential_1": {"label": "Residential-1 (R-1) Zone", "group": "Residential"},
    "socialized_housing": {"label": "Socialized Housing Zone", "group": "Residential"},
    "agri_industrial": {"label": "Agri-Industrial Zone", "group": "Industrial"},
    "industrial_1": {"label": "Industrial-1 (I-1) Zone", "group": "Industrial"},
    "industrial_2": {"label": "Industrial-2 (I-2) Zone", "group": "Industrial"},
    "industrial_3": {"label": "Industrial-3 (I-3) Zone", "group": "Industrial"},
    "general_institutional": {"label": "General Institutional Zone", "group": "Institutional & services"},
    "special_institutional": {"label": "Special Institutional Zone", "group": "Institutional & services"},
    "utilities_transport": {"label": "Utilities, Transportation and Services Zone", "group": "Institutional & services"},
    "parks_recreation": {"label": "Parks and Recreation Zone", "group": "Open space"},
    "cemetery": {"label": "Cemetery/Memorial Park Zone", "group": "Open space"},
    "buffer_greenbelt": {"label": "Buffer/Greenbelt Zone", "group": "Open space"},
    "production_agricultural": {"label": "Production Agricultural Sub-Zone", "group": "Agriculture & environment"},
    "aquaculture": {"label": "Aquaculture Sub-Zone", "group": "Agriculture & environment"},
    "mangrove": {"label": "Mangrove Sub-Zone", "group": "Agriculture & environment"},
    "forest_reserve": {"label": "Forest Reserve Sub-Zone", "group": "Agriculture & environment"},
    "quarry": {"label": "Quarry Sub-Zone", "group": "Agriculture & environment"},
    "special_use": {"label": "Special Used Zone", "group": "Agriculture & environment"},
}


# Zoning score a business gets in a zone where it is allowed (0 otherwise).
ZONING_ALLOWED_SCORE = 25


_ALL_BUSINESSES = ("coffee", "print", "laundry", "carwash", "kiosk", "water", "bakery", "pharmacy", "barber", "moto", "internet", "meat", "hardware")
_INDUSTRIAL_BUSINESSES = ("laundry", "carwash", "hardware", "moto")


# Starting allowed-uses table (zone -> business types), loosely following the
# HLURB model zoning ordinance. The admin edits the live copy in the database
# to match Panabo's zoning ordinance; zones left out allow nothing.
DEFAULT_ZONING_ALLOWED_USES = {
    "general_commercial": _ALL_BUSINESSES,
    "commercial_2": _ALL_BUSINESSES,
    "commercial_3": _ALL_BUSINESSES,
    "tourism": ("coffee", "kiosk", "bakery", "pharmacy", "barber", "water", "print", "internet"),
    "general_residential": ("kiosk", "water", "bakery", "pharmacy", "barber", "print", "laundry", "coffee", "internet", "meat"),
    "residential_1": ("kiosk", "water", "bakery", "barber"),
    "socialized_housing": ("kiosk", "water", "bakery", "barber"),
    "industrial_1": _INDUSTRIAL_BUSINESSES + ("water", "print"),
    "industrial_2": _INDUSTRIAL_BUSINESSES,
    "industrial_3": _INDUSTRIAL_BUSINESSES,
    "agri_industrial": _INDUSTRIAL_BUSINESSES,
    "general_institutional": ("kiosk", "coffee", "print", "pharmacy", "bakery"),
    "utilities_transport": ("kiosk", "coffee", "bakery", "pharmacy", "moto", "carwash", "water"),
    "parks_recreation": ("kiosk", "coffee"),
}


# The six zoning classes used before the LGU zones, and what they became.
LEGACY_ZONE_CLASSES = {
    "commercial": "general_commercial",
    "mixed_use": "commercial_2",
    "industrial": "agri_industrial",
    "residential": "general_residential",
    "institutional": "general_institutional",
    "agricultural": "production_agricultural",
}


# Their old scores; the one-time stack-order migration ranks overlaps by these.
LEGACY_ZONING_SCORES = {
    "commercial": 25,
    "mixed_use": 20,
    "industrial": 25,
    "residential": 10,
    "institutional": 5,
    "agricultural": 5,
}


ZONE_CLASSES_BY_CATEGORY = {
    "hazard": tuple(HAZARD_CLASS_VARS),
    "zoning": tuple(ZONING_CLASSES),
}


# Class given to imported polygons that carry no usable class; the admin reassigns it.
DEFAULT_IMPORT_CLASS = {
    "hazard": "high",
    "zoning": "general_commercial",
}


# The zoning boxes the system used before zoning became an admin layer.
BUILTIN_ZONING_CLASSES = {
    "commercial_proper": ("general_commercial", "Commercial center"),
    "industrial_anflo": ("agri_industrial", "Agri-industrial zone"),
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
