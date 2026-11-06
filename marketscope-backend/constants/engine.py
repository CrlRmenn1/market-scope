"""Every number the scoring engine uses, in one place.

Each value is marked with where it comes from:

  [study]  Carrido, Amba, Guevara & Claridades (2026), "Central Business District
           Likeliness Determination Using GIS, Volunteered Geographic Information,
           and Analytic Hierarchy Process: The Case of Quezon City, Philippines",
           ISPRS Annals X-5/W4-2025, 127-134.
           https://doi.org/10.5194/isprs-annals-X-5-W4-2025-127-2026
  [ours]   Our own calibration for Panabo. Not from a published source.

docs/ENGINE_METHODOLOGY.md explains the equations these feed.
"""

ENGINE_VERSION = "2.0"

# All factor scores share this scale, and potential = 4 * weighted sum gives 0-100.
FACTOR_MAX = 25.0
POTENTIAL_SCALE = 100.0 / FACTOR_MAX


# ---- road access ---------------------------------------------------------------

# Roads closer than this are searched; anything further scores nothing. [ours]
ROAD_SEARCH_M = 1000.0

# Share of the road score from reaching a major road vs the road at the door. [ours]
ROAD_MAJOR_SHARE = 0.6
ROAD_FRONTAGE_SHARE = 0.4

# Distance bands: (full value up to, half value at, zero at).
# Major road: 250 m and 500 m are [study] Table 2; 1000 m (zero) is [ours] because
# the study's lowest class has no upper limit.
ROAD_MAJOR_BANDS_M = (250.0, 500.0, 1000.0)
# Frontage: how good the road right at the site is. [ours]
ROAD_FRONTAGE_BANDS_M = (30.0, 100.0, 300.0)

# How much a road of each class counts, 0-1. [ours]
# The study treats trunk and primary as "major" [study]; Panabo has only 2 primary
# segments, so secondary and tertiary also count at a lower value.
ROAD_CLASS_VALUES = {
    "motorway": 1.0,
    "trunk": 1.0,
    "primary": 1.0,
    "secondary": 0.95,
    "tertiary": 0.85,
    "unclassified": 0.7,
    "residential": 0.6,
    "living_street": 0.6,
    "service": 0.4,
    "pedestrian": 0.3,
    "track": 0.2,
}
ROAD_MAJOR_CLASSES = frozenset({"motorway", "trunk", "primary", "secondary", "tertiary"})

# Classes kept out of road access: nothing with wheels reaches a shop this way.
ROAD_IGNORED_CLASSES = frozenset({"footway", "path", "cycleway", "steps", "bridleway"})


# ---- anchors -------------------------------------------------------------------

# (full value up to, half value at). Zero at ANCHOR_ZERO_FACTOR * the half distance.
# Bands are [study] Table 2 and Table 3, except education, which is [ours]: the
# study's survey dropped education for CBD-likeness, but schools matter to MSMEs.
ANCHOR_CATEGORIES = {
    "transit": {"label": "Transport terminal", "bands_m": (400.0, 800.0)},
    "market": {"label": "Market", "bands_m": (400.0, 800.0)},
    "commercial": {"label": "Mall / commercial", "bands_m": (400.0, 800.0)},
    "financial": {"label": "Bank / financial", "bands_m": (400.0, 800.0)},
    "government": {"label": "Government office", "bands_m": (400.0, 800.0)},
    "healthcare": {"label": "Hospital / healthcare", "bands_m": (300.0, 600.0)},
    "recreation": {"label": "Park / recreation", "bands_m": (500.0, 1000.0)},
    "education": {"label": "School", "bands_m": (400.0, 800.0)},
}
DEFAULT_ANCHOR_CATEGORY = "commercial"

# Avoids a cut-off at the outer band. [ours]
ANCHOR_ZERO_FACTOR = 1.5

ANCHOR_POWER_MIN = 1
ANCHOR_POWER_MAX = 25

# The importance choices on the admin page. [ours] (same range as the original list)
ANCHOR_POWER_TIERS = {"major": 25, "medium": 15, "minor": 5}

# An OSM anchor this close to a curated anchor of the same category is the same place. [ours]
ANCHOR_DEDUPE_M = 100.0

# created_by_admin_email of the original list once it is copied into the table.
ANCHOR_SEED_LABEL = "system-seed"

# Each business's anchor_target_power was set when only 8 anchors existed; this scales
# it for the full list so a busy area isn't simply at the maximum. [ours]
ANCHOR_TARGET_SCALE = 2.5

# Trend scans also try spots next to anchors at least this important. [ours]
TREND_LANDMARK_MIN_POWER = 20

# OSM tags that make a place an anchor: (key, value) -> (category, power). [ours]
# The tag families follow the study's use of OSM amenity/shop POIs. [study]
# Left out on purpose: ATMs, places of worship (mostly one day a week) and bus stops.
OSM_ANCHOR_TAGS = {
    ("shop", "mall"): ("commercial", 25),
    ("amenity", "marketplace"): ("market", 25),
    ("amenity", "bus_station"): ("transit", 25),
    ("public_transport", "station"): ("transit", 25),
    ("amenity", "university"): ("education", 25),
    ("amenity", "college"): ("education", 20),
    ("amenity", "hospital"): ("healthcare", 15),
    ("shop", "supermarket"): ("commercial", 15),
    ("shop", "department_store"): ("commercial", 15),
    ("amenity", "townhall"): ("government", 15),
    ("office", "government"): ("government", 15),
    ("leisure", "stadium"): ("recreation", 15),
    ("amenity", "school"): ("education", 10),
    ("amenity", "bank"): ("financial", 10),
    ("leisure", "park"): ("recreation", 10),
    ("leisure", "sports_centre"): ("recreation", 10),
    ("amenity", "clinic"): ("healthcare", 5),
    ("amenity", "doctors"): ("healthcare", 5),
    ("amenity", "fuel"): ("commercial", 5),
    ("amenity", "police"): ("government", 5),
    ("amenity", "fire_station"): ("government", 5),
    ("amenity", "post_office"): ("government", 5),
    ("amenity", "courthouse"): ("government", 5),
    ("amenity", "public_building"): ("government", 5),
    ("amenity", "community_centre"): ("recreation", 5),
}
# Every barangay has a hall, so these count far less than the City Hall. [ours]
OSM_BARANGAY_HALL_POWER = 5


# ---- competition ---------------------------------------------------------------

# A competitor's pull fades from 1 at the site to 0 here. 800 m is the outer band
# the study uses for commercial establishments. [study]
COMPETITION_REACH_M = 800.0

# score = 25 - COMPETITION_CURVE * log1p(pressure * sensitivity) [ours]
COMPETITION_CURVE = 7.0

# Same name this close together means the same shop listed twice. [ours]
COMPETITOR_DEDUPE_M = 30.0

# "No competitors" is only worth something where there are customers: empty land has
# no competitors either. So the competition score is credited in proportion to nearby
# demand, measured from these factors. The idea is the Index of Retail Saturation
# (LaLonde, 1961), which compares demand to supply. It normally uses households and
# spending; we have no such data, so anchors and buildings stand in for demand. [ours]
DEMAND_FACTORS = ("anchor", "building")


# ---- building density ----------------------------------------------------------

# Buildings fade from 1 at the site to 0 here, a short walking catchment. [ours]
BUILDING_REACH_M = 400.0

# score = BUILDING_CURVE * log1p(intensity * BUILDING_SCALE) [ours], set from the
# citywide distribution in scripts/calibrate_engine.py.
BUILDING_CURVE = 8.5
BUILDING_SCALE = 0.05


# ---- verdict -------------------------------------------------------------------

# Jenks natural breaks of the citywide scores (scripts/calibrate_engine.py: 437 grid
# points, all 13 business types, provisional weights), the method the study used to
# classify its map. [study] Re-run it after importing expert weights.
VERDICT_HIGH_MIN = 68
VERDICT_MODERATE_MIN = 47

# Very High flood hazard keeps a site out of the top class, whatever else it has. [ours]
HAZARD_VERY_HIGH_SCORE = 5

VERDICTS = {
    "highly_suitable": {"label": "Highly Suitable", "tone": "high"},
    "moderately_suitable": {"label": "Moderately Suitable", "tone": "medium"},
    "low_suitability": {"label": "Low Suitability", "tone": "low"},
    "not_permitted": {"label": "Not Permitted", "tone": "blocked"},
    "insufficient_data": {"label": "Not Enough Data", "tone": "unknown"},
}


# ---- business trend suggestions ------------------------------------------------

# OSM place types used to name areas. panabo.pbf has no barangay polygons, so a spot
# belongs to its nearest named place. [ours]
TREND_AREA_PLACE_TYPES = frozenset({"suburb", "quarter", "village"})

# A business's score in an area is the average of its best spots there, so one lucky
# point doesn't decide it. [ours]
TREND_AREA_TOP_SPOTS = 3

# Below this many known competitors citywide, "no competition" more likely means the
# shops aren't on record yet. Set from the citywide counts on 2026-11-06, where barber
# (2), meat (3) and hardware (5) sit under it. Reaching it doesn't prove the list is
# complete. [ours]
TREND_MIN_KNOWN_COMPETITORS = 6

# "Possible market gap": at most this many competitors within COMPETITION_REACH_M,
# where nearby demand is at least this share. 0.6 is about the top 30% of scanned
# spots. [ours]
TREND_GAP_MAX_COMPETITORS = 1
TREND_GAP_MIN_DEMAND = 0.6


# ---- AHP -----------------------------------------------------------------------

AHP_CRITERIA_LABELS = ["hazard", "market"]
AHP_MARKET_LABELS = ["competition", "road", "anchor", "building"]

# Used only if the weights table can't be read. Provisional hazard:market = 1:3. [ours]
FALLBACK_CRITERIA_WEIGHTS = (0.25, 0.75)

# Marks weights written by the proponents, not collected from experts.
AHP_PROVISIONAL_LABEL = "proponent-provisional"
AHP_EXPERT_LABEL_PREFIX = "expert-survey"
AHP_DUMMY_LABEL = "dummy-judgments"
