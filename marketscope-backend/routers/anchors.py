"""Admin routes for anchors: places that bring people to an area and raise a site's score.

The admin can add anchors OpenStreetMap doesn't have, and correct or hide the ones it
gets wrong. Saves go to verified_local_features; services/anchors.py does the merging.
"""
import psycopg2
from fastapi import APIRouter, Header, HTTPException
from psycopg2.extras import RealDictCursor

from constants.engine import (
    ANCHOR_CATEGORIES,
    ANCHOR_POWER_MAX,
    ANCHOR_POWER_MIN,
    ANCHOR_POWER_TIERS,
)
from constants.geo import PANABO_BOUNDS
from core.auth import internal_error
from core.config import ADMIN_EMAIL
from core.database import DB_CONFIG
from core.security import verify_admin_token
from db.schema import ensure_verified_local_features_table
from models.requests import AdminAnchorRequest
from services.anchors import list_all_anchors
from services.map_layers import mark_scoring_data_changed
from services.osm_data import get_osm_anchor_features
from utils.geo import check_inside_bounds


router = APIRouter()


ANCHOR_RETURNING = (
    "id, name, feature_subtype, latitude, longitude, power, source_note, is_active, "
    "osm_ref, created_by_admin_email, created_at, updated_at"
)


def validate_anchor_payload(payload: AdminAnchorRequest):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the anchor a name.")
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="Anchor names can be at most 200 characters.")
    if payload.category not in ANCHOR_CATEGORIES:
        raise HTTPException(status_code=400, detail="Choose one of the anchor categories.")
    if not ANCHOR_POWER_MIN <= payload.power <= ANCHOR_POWER_MAX:
        raise HTTPException(status_code=400, detail=f"Importance must be between {ANCHOR_POWER_MIN} and {ANCHOR_POWER_MAX}.")
    if not check_inside_bounds(payload.latitude, payload.longitude, PANABO_BOUNDS):
        raise HTTPException(status_code=400, detail="That location is outside Panabo City.")
    return name


@router.get("/admin/anchors")
def admin_list_anchors(x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(cursor)
        anchors = list_all_anchors(cursor)
        cursor.close()
        conn.close()
    except Exception as e:
        raise internal_error(e, "admin_list_anchors")

    return {
        "status": "success",
        "anchors": anchors,
        "categories": ANCHOR_CATEGORIES,
        "power_tiers": ANCHOR_POWER_TIERS,
        "bounds": PANABO_BOUNDS,
    }


@router.post("/admin/anchors")
def admin_create_anchor(payload: AdminAnchorRequest, x_admin_token: str | None = Header(default=None)):
    """A new anchor. With osm_ref, it is a correction of that OSM anchor instead, and
    with is_active=false too, it hides that OSM anchor."""
    verify_admin_token(x_admin_token)
    name = validate_anchor_payload(payload)

    if payload.osm_ref and not any(feature["osm_ref"] == payload.osm_ref for feature in get_osm_anchor_features()):
        raise HTTPException(status_code=404, detail="That OpenStreetMap anchor no longer exists.")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(cursor)
        cursor.execute(
            f"""
            INSERT INTO verified_local_features (
                feature_kind, name, feature_subtype, latitude, longitude, power,
                source_note, is_active, osm_ref, created_by_admin_email
            ) VALUES ('anchor', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (osm_ref) WHERE osm_ref IS NOT NULL DO UPDATE SET
                name = EXCLUDED.name,
                feature_subtype = EXCLUDED.feature_subtype,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                power = EXCLUDED.power,
                source_note = EXCLUDED.source_note,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
            RETURNING {ANCHOR_RETURNING}
            """,
            (
                name,
                payload.category,
                payload.latitude,
                payload.longitude,
                payload.power,
                (payload.note or "").strip() or None,
                payload.is_active,
                payload.osm_ref,
                ADMIN_EMAIL,
            ),
        )
        created = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        raise internal_error(e, "admin_create_anchor")

    mark_scoring_data_changed()
    return {"status": "success", "anchor_id": created["id"]}


@router.put("/admin/anchors/{anchor_id}")
def admin_update_anchor(anchor_id: int, payload: AdminAnchorRequest, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    name = validate_anchor_payload(payload)

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(cursor)
        cursor.execute(
            f"""
            UPDATE verified_local_features
            SET name = %s, feature_subtype = %s, latitude = %s, longitude = %s, power = %s,
                source_note = %s, is_active = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND feature_kind = 'anchor'
            RETURNING {ANCHOR_RETURNING}
            """,
            (
                name,
                payload.category,
                payload.latitude,
                payload.longitude,
                payload.power,
                (payload.note or "").strip() or None,
                payload.is_active,
                anchor_id,
            ),
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        raise internal_error(e, "admin_update_anchor")

    if not updated:
        raise HTTPException(status_code=404, detail="Anchor not found.")

    mark_scoring_data_changed()
    return {"status": "success", "anchor_id": updated["id"]}


@router.delete("/admin/anchors/{anchor_id}")
def admin_delete_anchor(anchor_id: int, x_admin_token: str | None = Header(default=None)):
    """Deletes an added anchor. For an OSM anchor this removes the correction, so the
    original OSM values come back."""
    verify_admin_token(x_admin_token)

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        ensure_verified_local_features_table(cursor)
        cursor.execute(
            "DELETE FROM verified_local_features WHERE id = %s AND feature_kind = 'anchor' RETURNING id",
            (anchor_id,),
        )
        deleted = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        raise internal_error(e, "admin_delete_anchor")

    if not deleted:
        raise HTTPException(status_code=404, detail="Anchor not found.")

    mark_scoring_data_changed()
    return {"status": "success", "deleted_anchor_id": deleted[0]}
