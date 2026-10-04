"""Admin routes for custom MSME entries."""
import psycopg2
from fastapi import APIRouter, HTTPException, Header
from psycopg2.extras import RealDictCursor

from core.database import DB_CONFIG
from core.security import verify_admin_token
from db.schema import ensure_custom_msme_table
from models.requests import AdminCreateMsme, AdminUpdateMsme


router = APIRouter()


@router.get("/admin/custom-msmes")
def admin_list_custom_msmes(x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_custom_msme_table(cursor)
        cursor.execute(
            """
            SELECT id, name, business_type, latitude, longitude, created_at
            FROM custom_msme
            ORDER BY created_at DESC, id DESC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"status": "success", "custom_msmes": rows}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/custom-msmes")
def admin_create_custom_msme(payload: AdminCreateMsme, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_custom_msme_table(cursor)
        cursor.execute(
            """
            INSERT INTO custom_msme (name, business_type, latitude, longitude)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, business_type, latitude, longitude, created_at
            """,
            (payload.name, payload.business_type, payload.latitude, payload.longitude)
        )
        created = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "custom_msme": created}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/admin/custom-msmes/{msme_id}")
def admin_update_custom_msme(msme_id: int, payload: AdminUpdateMsme, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_custom_msme_table(cursor)
        cursor.execute(
            """
            UPDATE custom_msme
            SET name = %s, business_type = %s, latitude = %s, longitude = %s
            WHERE id = %s
            RETURNING id, name, business_type, latitude, longitude, created_at
            """,
            (payload.name, payload.business_type, payload.latitude, payload.longitude, msme_id)
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not updated:
            raise HTTPException(status_code=404, detail="Custom MSME not found")

        return {"status": "success", "custom_msme": updated}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/custom-msmes/{msme_id}")
def admin_delete_custom_msme(msme_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        ensure_custom_msme_table(cursor)
        cursor.execute("DELETE FROM custom_msme WHERE id = %s RETURNING id", (msme_id,))
        deleted = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not deleted:
            raise HTTPException(status_code=404, detail="Custom MSME not found")

        return {"status": "success", "deleted_custom_msme_id": deleted[0]}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
