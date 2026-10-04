"""Commercial space submissions (user and admin) and map markers."""
import psycopg2
from fastapi import APIRouter, HTTPException, Header
from psycopg2.extras import Json, RealDictCursor

from core.config import ADMIN_EMAIL
from core.database import DB_CONFIG
from core.security import verify_admin_token
from db.schema import (
    ensure_admin_space_submissions_table,
    ensure_user_space_submissions_table,
    get_users_primary_key_column,
)
from models.requests import (
    AdminReviewUserSpaceSubmissionRequest,
    AdminSpaceSubmissionRequest,
    AdminToggleSpaceSubmissionActiveRequest,
    UserSpaceSubmissionRequest,
)
from services.spaces import fetch_active_space_markers_for_analysis


router = APIRouter()


def normalize_listing_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    if mode not in {"rent", "buy"}:
        raise HTTPException(status_code=400, detail="listing_mode must be either 'rent' or 'buy'")
    return mode


def normalize_guarantee_level(value: str) -> str:
    level = str(value or "").strip().lower()
    if level not in {"guaranteed", "potential"}:
        raise HTTPException(status_code=400, detail="guarantee_level must be either 'guaranteed' or 'potential'")
    return level


def normalize_space_submission_status(value: str) -> str:
    status = str(value or "").strip().lower()
    if status not in {"pending", "approved", "rejected", "archived"}:
        raise HTTPException(status_code=400, detail="status must be pending, approved, rejected, or archived")
    return status


@router.post("/spaces/user-submissions")
def create_user_space_submission(payload: UserSpaceSubmissionRequest):
    try:
        listing_mode = normalize_listing_mode(payload.listing_mode)

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        ensure_user_space_submissions_table(cursor, user_pk_column)

        cursor.execute(
            f"SELECT {user_pk_column} AS user_id FROM users WHERE {user_pk_column} = %s",
            (payload.user_id,)
        )
        existing_user = cursor.fetchone()
        if not existing_user:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        cursor.execute(
            """
            INSERT INTO user_space_submissions (
                submitted_by_user_id,
                title,
                listing_mode,
                guarantee_level,
                property_type,
                business_type,
                latitude,
                longitude,
                address_text,
                price_min,
                price_max,
                contact_info,
                notes,
                photo_urls,
                status
            )
            VALUES (%s, %s, %s, 'guaranteed', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING *
            """,
            (
                payload.user_id,
                payload.title,
                listing_mode,
                (payload.property_type or None),
                (payload.business_type or None),
                payload.latitude,
                payload.longitude,
                (payload.address_text or None),
                payload.price_min,
                payload.price_max,
                (payload.contact_info or None),
                (payload.notes or None),
                Json(payload.photo_urls or []),
            )
        )
        created = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "submission": created}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spaces/map-markers")
def list_space_map_markers():
    try:
        markers = fetch_active_space_markers_for_analysis()

        for marker in markers:
            marker["last_verified_at"] = marker.get("verified_at")

        return {"status": "success", "markers": markers}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/spaces/user-submissions")
def admin_list_user_space_submissions(status: str | None = None, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        normalized_status = normalize_space_submission_status(status) if status else None

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        ensure_user_space_submissions_table(cursor, user_pk_column)

        if normalized_status:
            cursor.execute(
                "SELECT * FROM user_space_submissions WHERE status = %s ORDER BY created_at DESC, id DESC",
                (normalized_status,)
            )
        else:
            cursor.execute("SELECT * FROM user_space_submissions ORDER BY created_at DESC, id DESC")

        rows = cursor.fetchall() or []
        cursor.close()
        conn.close()
        return {"status": "success", "submissions": rows}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/admin/spaces/user-submissions/{submission_id}/status")
def admin_update_user_space_submission_status(
    submission_id: int,
    payload: AdminReviewUserSpaceSubmissionRequest,
    x_admin_token: str | None = Header(default=None)
):
    verify_admin_token(x_admin_token)
    try:
        normalized_status = normalize_space_submission_status(payload.status)

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        ensure_user_space_submissions_table(cursor, user_pk_column)

        cursor.execute(
            """
            UPDATE user_space_submissions
            SET
                status = %s,
                review_note = %s,
                reviewed_by_admin_email = %s,
                reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
            """,
            (normalized_status, (payload.review_note or None), ADMIN_EMAIL, submission_id)
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not updated:
            raise HTTPException(status_code=404, detail="User space submission not found")

        return {"status": "success", "submission": updated}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/spaces/admin-submissions")
def admin_list_admin_space_submissions(x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_admin_space_submissions_table(cursor)
        cursor.execute("SELECT * FROM admin_space_submissions ORDER BY created_at DESC, id DESC")
        rows = cursor.fetchall() or []
        cursor.close()
        conn.close()
        return {"status": "success", "submissions": rows}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/spaces/admin-submissions")
def admin_create_admin_space_submission(
    payload: AdminSpaceSubmissionRequest,
    x_admin_token: str | None = Header(default=None)
):
    verify_admin_token(x_admin_token)
    try:
        listing_mode = normalize_listing_mode(payload.listing_mode)
        guarantee_level = normalize_guarantee_level(payload.guarantee_level)
        confidence_score = payload.confidence_score

        if confidence_score is not None and (confidence_score < 0 or confidence_score > 100):
            raise HTTPException(status_code=400, detail="confidence_score must be between 0 and 100")

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_admin_space_submissions_table(cursor)
        cursor.execute(
            """
            INSERT INTO admin_space_submissions (
                title,
                listing_mode,
                guarantee_level,
                confidence_score,
                property_type,
                business_type,
                latitude,
                longitude,
                address_text,
                price_min,
                price_max,
                source_note,
                contact_info,
                notes,
                photo_urls,
                verified_at,
                expires_at,
                is_active,
                created_by_admin_email
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                payload.title,
                listing_mode,
                guarantee_level,
                confidence_score,
                (payload.property_type or None),
                (payload.business_type or None),
                payload.latitude,
                payload.longitude,
                (payload.address_text or None),
                payload.price_min,
                payload.price_max,
                (payload.source_note or None),
                (payload.contact_info or None),
                (payload.notes or None),
                Json(payload.photo_urls or []),
                payload.verified_at,
                payload.expires_at,
                payload.is_active,
                ADMIN_EMAIL,
            )
        )
        created = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "submission": created}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/admin/spaces/admin-submissions/{submission_id}/active")
def admin_update_admin_space_submission_active_state(
    submission_id: int,
    payload: AdminToggleSpaceSubmissionActiveRequest,
    x_admin_token: str | None = Header(default=None)
):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_admin_space_submissions_table(cursor)

        cursor.execute(
            """
            UPDATE admin_space_submissions
            SET
                is_active = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
            """,
            (payload.is_active, submission_id)
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not updated:
            raise HTTPException(status_code=404, detail="Admin space submission not found")

        return {"status": "success", "submission": updated}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
