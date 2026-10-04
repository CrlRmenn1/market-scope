"""Admin login route."""
import bcrypt
import psycopg2
from fastapi import APIRouter, HTTPException
from psycopg2.extras import RealDictCursor

from core.config import ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_TOKEN
from core.database import DB_CONFIG
from db.schema import ensure_admin_users_table
from models.requests import AdminLoginRequest


router = APIRouter()


@router.post("/admin/login")
def admin_login(payload: AdminLoginRequest):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_admin_users_table(cursor)

        cursor.execute(
            """
            SELECT email, password_hash
            FROM admin_users
            WHERE email = %s
            LIMIT 1
            """,
            (payload.email,)
        )
        admin_row = cursor.fetchone()

        cursor.close()
        conn.close()

        if admin_row:
            stored_hash = str(admin_row.get("password_hash") or "")
            is_valid = False
            try:
                is_valid = bcrypt.checkpw(payload.password.encode("utf-8"), stored_hash.encode("utf-8"))
            except Exception:
                is_valid = payload.password == stored_hash

            if is_valid:
                return {
                    "status": "success",
                    "admin": {
                        "email": admin_row.get("email") or payload.email,
                        "token": ADMIN_TOKEN
                    }
                }

        # Backward-compatible fallback to env credentials.
        if payload.email == ADMIN_EMAIL and payload.password == ADMIN_PASSWORD:
            return {
                "status": "success",
                "admin": {
                    "email": ADMIN_EMAIL,
                    "token": ADMIN_TOKEN
                }
            }

        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
