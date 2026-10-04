"""Admin routes for verified local features (MSMEs, anchors, roads, buildings)."""
import psycopg2
from fastapi import APIRouter, HTTPException, Header
from psycopg2.extras import RealDictCursor

from constants.msme import VERIFIED_LOCAL_FEATURE_KINDS
from core.database import DB_CONFIG
from core.security import verify_admin_token
from db.schema import ensure_verified_local_features_table
from models.requests import AdminVerifiedLocalFeatureRequest
from utils.values import normalize_osm_value


router = APIRouter()


@router.get("/admin/verified-local-features")
def admin_list_verified_local_features(
    feature_kind: str | None = None,
    business_type: str | None = None,
    include_inactive: bool = False,
    x_admin_token: str | None = Header(default=None)
):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(cursor)

        query = [
            "SELECT id, feature_kind, name, business_type, feature_subtype, latitude, longitude, road_class, power, building_type, landuse, area_m2, confidence_score, source_note, is_active, verified_at, created_by_admin_email, created_at, updated_at",
            "FROM verified_local_features",
            "WHERE 1 = 1",
        ]
        params = []

        if feature_kind:
            normalized_kind = normalize_osm_value(feature_kind)
            if normalized_kind not in VERIFIED_LOCAL_FEATURE_KINDS:
                raise HTTPException(status_code=400, detail="Invalid verified feature kind")
            query.append("AND feature_kind = %s")
            params.append(normalized_kind)

        if business_type:
            query.append("AND LOWER(TRIM(COALESCE(business_type, ''))) = %s")
            params.append(normalize_osm_value(business_type))

        if not include_inactive:
            query.append("AND is_active = TRUE")

        query.append("ORDER BY updated_at DESC, created_at DESC, id DESC")
        cursor.execute("\n".join(query), params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"status": "success", "verified_local_features": rows}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/verified-local-features")
def admin_create_verified_local_feature(payload: AdminVerifiedLocalFeatureRequest, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        feature_kind = normalize_osm_value(payload.feature_kind)
        if feature_kind not in VERIFIED_LOCAL_FEATURE_KINDS:
            raise HTTPException(status_code=400, detail="Invalid verified feature kind")

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(cursor)
        cursor.execute(
            """
            INSERT INTO verified_local_features (
                feature_kind, name, business_type, feature_subtype, latitude, longitude,
                road_class, power, building_type, landuse, area_m2, confidence_score,
                source_note, is_active, verified_at, created_by_admin_email
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, feature_kind, name, business_type, feature_subtype, latitude, longitude, road_class, power, building_type, landuse, area_m2, confidence_score, source_note, is_active, verified_at, created_by_admin_email, created_at, updated_at
            """,
            (
                feature_kind,
                payload.name,
                payload.business_type,
                payload.feature_subtype,
                payload.latitude,
                payload.longitude,
                payload.road_class,
                payload.power,
                payload.building_type,
                payload.landuse,
                payload.area_m2,
                int(payload.confidence_score or 0),
                payload.source_note,
                payload.is_active,
                payload.verified_at,
                None,
            )
        )
        created = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "verified_local_feature": created}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/admin/verified-local-features/{feature_id}")
def admin_update_verified_local_feature(feature_id: int, payload: AdminVerifiedLocalFeatureRequest, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        feature_kind = normalize_osm_value(payload.feature_kind)
        if feature_kind not in VERIFIED_LOCAL_FEATURE_KINDS:
            raise HTTPException(status_code=400, detail="Invalid verified feature kind")

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(cursor)
        cursor.execute(
            """
            UPDATE verified_local_features
            SET feature_kind = %s,
                name = %s,
                business_type = %s,
                feature_subtype = %s,
                latitude = %s,
                longitude = %s,
                road_class = %s,
                power = %s,
                building_type = %s,
                landuse = %s,
                area_m2 = %s,
                confidence_score = %s,
                source_note = %s,
                is_active = %s,
                verified_at = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, feature_kind, name, business_type, feature_subtype, latitude, longitude, road_class, power, building_type, landuse, area_m2, confidence_score, source_note, is_active, verified_at, created_by_admin_email, created_at, updated_at
            """,
            (
                feature_kind,
                payload.name,
                payload.business_type,
                payload.feature_subtype,
                payload.latitude,
                payload.longitude,
                payload.road_class,
                payload.power,
                payload.building_type,
                payload.landuse,
                payload.area_m2,
                int(payload.confidence_score or 0),
                payload.source_note,
                payload.is_active,
                payload.verified_at,
                feature_id,
            )
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not updated:
            raise HTTPException(status_code=404, detail="Verified local feature not found")

        return {"status": "success", "verified_local_feature": updated}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/verified-local-features/{feature_id}")
def admin_delete_verified_local_feature(feature_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        ensure_verified_local_features_table(cursor)
        cursor.execute("DELETE FROM verified_local_features WHERE id = %s RETURNING id", (feature_id,))
        deleted = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not deleted:
            raise HTTPException(status_code=404, detail="Verified local feature not found")

        return {"status": "success", "deleted_verified_local_feature_id": deleted[0]}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
