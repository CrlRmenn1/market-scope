"""MSME business categories, their scoring profiles, and OSM matching tables."""


VERIFIED_LOCAL_FEATURE_KINDS = {"msme", "anchor", "road", "building"}


SME_DATABASE = {
    "coffee": {"key": "amenity", "val": "cafe", "fear": 6, "need": 9, "name": "Coffee Shops", "osm_tags": [("amenity", "cafe"), ("shop", "coffee")]},
    "print": {"key": "shop", "val": "copyshop", "fear": 7, "need": 6, "name": "Print/Copy Centers", "osm_tags": [("shop", "copyshop"), ("shop", "stationery"), ("shop", "books")]},
    "laundry": {"key": "shop", "val": "laundry", "fear": 9, "need": 7, "name": "Laundry Shops", "osm_tags": [("shop", "laundry"), ("shop", "dry_cleaning")]},
    "carwash": {"key": "amenity", "val": "car_wash", "fear": 8, "need": 9, "name": "Car Washes", "osm_tags": [("amenity", "car_wash")]},
    "kiosk": {"key": "amenity", "val": "fast_food", "fear": 6, "need": 9, "name": "Food Kiosks/Stalls", "osm_tags": [("amenity", "fast_food"), ("amenity", "food_court"), ("shop", "kiosk")]},
    "water": {"key": "shop", "val": "water", "fear": 4, "need": 7, "name": "Water Refilling Stations", "osm_tags": [("shop", "water")]},
    "bakery": {"key": "shop", "val": "bakery", "fear": 8, "need": 9, "name": "Bakeries", "osm_tags": [("shop", "bakery"), ("shop", "pastry")]},
    "pharmacy": {"key": "amenity", "val": "pharmacy", "fear": 7, "need": 9, "name": "Small Pharmacies", "osm_tags": [("amenity", "pharmacy"), ("shop", "chemist")]},
    "barber": {"key": "shop", "val": "hairdresser", "fear": 7, "need": 9, "name": "Barbershops/Salons", "osm_tags": [("shop", "hairdresser"), ("shop", "beauty")]},
    "moto": {"key": "shop", "val": "motorcycle_repair", "fear": 5, "need": 8, "name": "Motorcycle Repair/Parts & Accessories", "osm_tags": [("shop", "motorcycle"), ("shop", "motorcycle_repair"), ("shop", "car_repair"), ("shop", "car_parts")]},
    "internet": {"key": "amenity", "val": "internet_cafe", "fear": 6, "need": 6, "name": "Internet Cafes", "osm_tags": [("amenity", "internet_cafe")]},
    "meat": {"key": "shop", "val": "butcher", "fear": 9, "need": 9, "name": "Meat Shops", "osm_tags": [("shop", "butcher"), ("shop", "deli")]},
    "hardware": {"key": "shop", "val": "hardware", "fear": 7, "need": 8, "name": "Hardware/Construction Supplies", "osm_tags": [("shop", "hardware"), ("shop", "doityourself"), ("shop", "trade")]}
}


MSME_CATEGORY_PROFILES = {
    "coffee": {
        "display_name": "Coffee Shops",
        "osm_tags": [("amenity", "cafe"), ("shop", "coffee")],
        "competition_sensitivity": 1.38,
        "competition_weight": 0.47,
        "road_weight": 0.20,
        "anchor_weight": 0.19,
        "building_weight": 0.14,
        "anchor_target_power": 40.0,
    },
    "print": {
        "display_name": "Print/Copy Centers",
        "osm_tags": [("shop", "copyshop"), ("shop", "stationery"), ("shop", "books")],
        "competition_sensitivity": 1.12,
        "competition_weight": 0.42,
        "road_weight": 0.23,
        "anchor_weight": 0.18,
        "building_weight": 0.17,
        "anchor_target_power": 34.0,
    },
    "laundry": {
        "display_name": "Laundry Shops",
        "osm_tags": [("shop", "laundry"), ("shop", "dry_cleaning")],
        "competition_sensitivity": 1.18,
        "competition_weight": 0.43,
        "road_weight": 0.20,
        "anchor_weight": 0.19,
        "building_weight": 0.18,
        "anchor_target_power": 36.0,
    },
    "carwash": {
        "display_name": "Car Washes",
        "osm_tags": [("amenity", "car_wash")],
        "competition_sensitivity": 1.10,
        "competition_weight": 0.39,
        "road_weight": 0.28,
        "anchor_weight": 0.16,
        "building_weight": 0.17,
        "anchor_target_power": 38.0,
    },
    "kiosk": {
        "display_name": "Food Kiosks/Stalls",
        "osm_tags": [("amenity", "fast_food"), ("amenity", "food_court"), ("shop", "kiosk")],
        "competition_sensitivity": 1.34,
        "competition_weight": 0.44,
        "road_weight": 0.18,
        "anchor_weight": 0.22,
        "building_weight": 0.16,
        "anchor_target_power": 42.0,
    },
    "water": {
        "display_name": "Water Refilling Stations",
        "osm_tags": [("shop", "water")],
        "competition_sensitivity": 0.98,
        "competition_weight": 0.36,
        "road_weight": 0.22,
        "anchor_weight": 0.18,
        "building_weight": 0.24,
        "anchor_target_power": 30.0,
    },
    "bakery": {
        "display_name": "Bakeries",
        "osm_tags": [("shop", "bakery"), ("shop", "pastry")],
        "competition_sensitivity": 1.28,
        "competition_weight": 0.44,
        "road_weight": 0.20,
        "anchor_weight": 0.19,
        "building_weight": 0.17,
        "anchor_target_power": 38.0,
    },
    "pharmacy": {
        "display_name": "Small Pharmacies",
        "osm_tags": [("amenity", "pharmacy"), ("shop", "chemist")],
        "competition_sensitivity": 1.22,
        "competition_weight": 0.43,
        "road_weight": 0.21,
        "anchor_weight": 0.22,
        "building_weight": 0.14,
        "anchor_target_power": 40.0,
    },
    "barber": {
        "display_name": "Barbershops/Salons",
        "osm_tags": [("shop", "hairdresser"), ("shop", "beauty")],
        "competition_sensitivity": 1.24,
        "competition_weight": 0.45,
        "road_weight": 0.19,
        "anchor_weight": 0.20,
        "building_weight": 0.16,
        "anchor_target_power": 39.0,
    },
    "moto": {
        "display_name": "Motorcycle Repair/Parts & Accessories",
        "osm_tags": [("shop", "motorcycle"), ("shop", "motorcycle_repair"), ("shop", "car_repair"), ("shop", "car_parts")],
        "competition_sensitivity": 1.06,
        "competition_weight": 0.40,
        "road_weight": 0.30,
        "anchor_weight": 0.14,
        "building_weight": 0.16,
        "anchor_target_power": 32.0,
    },
    "internet": {
        "display_name": "Internet Cafes",
        "osm_tags": [("amenity", "internet_cafe")],
        "competition_sensitivity": 1.15,
        "competition_weight": 0.41,
        "road_weight": 0.21,
        "anchor_weight": 0.20,
        "building_weight": 0.18,
        "anchor_target_power": 34.0,
    },
    "meat": {
        "display_name": "Meat Shops",
        "osm_tags": [("shop", "butcher"), ("shop", "deli")],
        "competition_sensitivity": 1.20,
        "competition_weight": 0.42,
        "road_weight": 0.20,
        "anchor_weight": 0.20,
        "building_weight": 0.18,
        "anchor_target_power": 35.0,
    },
    "hardware": {
        "display_name": "Hardware/Construction Supplies",
        "osm_tags": [("shop", "hardware"), ("shop", "doityourself"), ("shop", "trade")],
        "competition_sensitivity": 1.04,
        "competition_weight": 0.40,
        "road_weight": 0.30,
        "anchor_weight": 0.14,
        "building_weight": 0.16,
        "anchor_target_power": 30.0,
    },
}


# How each business type is usually set up. Matches the "Preferred Setup" choices
# in the trend preferences; used to find other businesses that fit the user's setup.
TYPICAL_SETUP = {
    "coffee": "storefront",
    "print": "storefront",
    "laundry": "storefront",
    "carwash": "roadside",
    "kiosk": "kiosk",
    "water": "storefront",
    "bakery": "storefront",
    "pharmacy": "storefront",
    "barber": "storefront",
    "moto": "roadside",
    "internet": "storefront",
    "meat": "market-stall",
    "hardware": "warehouse",
}


SME_PROFILE_BY_NAME = {
    str(profile.get("name") or "").strip().lower(): key
    for key, profile in SME_DATABASE.items()
    if str(profile.get("name") or "").strip()
}
# Older profiles saved a category's previous display name.
SME_PROFILE_BY_NAME["motorcycle repair shops"] = "moto"


# Whole-word matches on a business name, used alongside the OSM tags
# (services/osm_data.py). Keep these specific: "wash" alone would make a car wash a laundry.
PBF_NAME_KEYWORD_FALLBACK = {
    "coffee": ["coffee", "cafe"],
    "print": ["print", "printing", "photocopy", "xerox"],
    "laundry": ["laundry", "laundromat", "labandera", "dry clean", "dry cleaning"],
    "carwash": ["car wash", "carwash", "autowash", "auto spa"],
    "kiosk": ["kiosk", "snack", "snacks"],
    "water": ["water refilling", "water station", "purified water"],
    "bakery": ["bakery", "bakeshop", "bread", "panaderia"],
    "pharmacy": ["pharmacy", "drugstore", "mercury drug"],
    "barber": ["barber", "barbershop", "salon", "hair"],
    "moto": ["motorcycle", "moto", "motor parts", "motorparts"],
    "internet": ["internet", "cyber", "computer shop"],
    "meat": ["meat", "meats", "butcher"],
    "hardware": ["hardware", "construction supply", "construction supplies"],
}


COMMERCIAL_AMENITY_VALUES = {
    "cafe", "restaurant", "fast_food", "food_court", "pharmacy", "bank", "fuel", "marketplace",
    "car_wash", "clinic", "hospital", "internet_cafe", "bar", "pub", "biergarten"
}


DEFAULT_MSME_ANALYSIS_PROFILE = {
    "display_name": "MSME",
    "osm_tags": [("shop", "convenience")],
    "competition_sensitivity": 1.0,
    "competition_weight": 0.42,
    "road_weight": 0.23,
    "anchor_weight": 0.20,
    "building_weight": 0.15,
    "anchor_target_power": 36.0,
}
