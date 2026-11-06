"""The anchors a scan counts, merged from three sources:

  1. admin anchors  - placed on the admin Anchors page (verified_local_features)
  2. seeded anchors - the original built-in list, copied into the same table once
  3. OSM anchors    - places in panabo.pbf (constants/engine.py OSM_ANCHOR_TAGS)

OSM data isn't always right, so a table row with an osm_ref corrects or hides that
OSM anchor. An OSM anchor right next to a curated one of the same category is taken
to be the same place, so nothing counts twice.
"""
from constants.engine import ANCHOR_DEDUPE_M, ANCHOR_SEED_LABEL, TREND_LANDMARK_MIN_POWER
from constants.geo import PANABO_ANCHORS
from db.queries import fetch_verified_local_features
from services.osm_data import get_osm_anchor_features
from services.value_functions import anchor_category
from utils.geo import calculate_distance


STATUS_ACTIVE = "active"
STATUS_HIDDEN = "hidden"
STATUS_DUPLICATE = "duplicate"


def _anchor_from_row(row):
    return {
        "id": row.get("id"),
        "osm_ref": row.get("osm_ref"),
        "origin": "seed" if row.get("created_by_admin_email") == ANCHOR_SEED_LABEL else "admin",
        "name": row.get("name"),
        "category": anchor_category(row.get("feature_subtype")),
        "power": row.get("power") or 0,
        "lat": row.get("latitude"),
        "lon": row.get("longitude"),
        "note": row.get("source_note"),
        "status": STATUS_ACTIVE if row.get("is_active", True) else STATUS_HIDDEN,
    }


def merge_anchors(rows, osm_features):
    """Every anchor with a status; only STATUS_ACTIVE ones count in a scan."""
    rows = rows or []
    overrides = {row["osm_ref"]: row for row in rows if row.get("osm_ref")}
    merged = [_anchor_from_row(row) for row in rows if not row.get("osm_ref")]
    curated = [anchor for anchor in merged if anchor["status"] == STATUS_ACTIVE]

    for feature in osm_features or []:
        override = overrides.get(feature["osm_ref"])
        if override is not None:
            anchor = _anchor_from_row(override)
            anchor["origin"] = "osm"
            anchor["edited"] = True
            anchor["tag"] = feature.get("tag")
            merged.append(anchor)
            continue

        anchor = {
            "id": None,
            "osm_ref": feature["osm_ref"],
            "origin": "osm",
            "name": feature["name"],
            "category": feature["category"],
            "power": feature["power"],
            "lat": feature["lat"],
            "lon": feature["lon"],
            "note": None,
            "tag": feature.get("tag"),
            "status": STATUS_ACTIVE,
        }
        same_place = next(
            (
                other for other in curated
                if other["category"] == anchor["category"]
                and calculate_distance(other["lat"], other["lon"], anchor["lat"], anchor["lon"]) <= ANCHOR_DEDUPE_M
            ),
            None,
        )
        if same_place is not None:
            anchor["status"] = STATUS_DUPLICATE
            anchor["duplicate_of"] = same_place["name"]
        merged.append(anchor)

    return merged


def _builtin_anchor_rows():
    """The original list in row form, for when the table can't be read."""
    return [
        {
            "name": anchor["name"],
            "feature_subtype": anchor["category"],
            "power": anchor["power"],
            "latitude": anchor["lat"],
            "longitude": anchor["lon"],
            "created_by_admin_email": ANCHOR_SEED_LABEL,
        }
        for anchor in PANABO_ANCHORS
    ]


def list_all_anchors(cursor=None):
    """Everything, hidden and duplicate included (the admin page). May raise on a DB error."""
    rows = fetch_verified_local_features("anchor", active_only=False, cursor=cursor, strict=True)
    return merge_anchors(rows, get_osm_anchor_features())


def get_scoring_anchors(cursor=None):
    """(anchors a scan counts, warnings). A database failure never empties the list."""
    warnings = []
    try:
        rows = fetch_verified_local_features("anchor", active_only=False, cursor=cursor, strict=True)
    except Exception as exc:
        print(f"Anchor table read failed, using the built-in list: {exc}")
        rows = _builtin_anchor_rows()
        warnings.append("Admin-added anchors couldn't be read, so only the built-in and OSM anchors were counted.")

    anchors = [anchor for anchor in merge_anchors(rows, get_osm_anchor_features()) if anchor["status"] == STATUS_ACTIVE]
    return anchors, warnings


def get_trend_landmarks(cursor=None):
    """Anchors worth checking as trend spots: curated ones and the major OSM places."""
    anchors, _ = get_scoring_anchors(cursor)
    return [
        anchor for anchor in anchors
        if anchor["origin"] != "osm" or anchor["power"] >= TREND_LANDMARK_MIN_POWER
    ]
