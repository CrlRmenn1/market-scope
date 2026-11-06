"""Admin login route."""
import hmac

import bcrypt
import psycopg2
from fastapi import APIRouter, HTTPException, Request
from psycopg2.extras import RealDictCursor

from core.auth import internal_error
from core.config import ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_TOKEN
from core.database import DB_CONFIG
from core.rate_limit import check_rate_limit, client_ip
from db.schema import ensure_admin_users_table
from models.requests import AdminLoginRequest


router = APIRouter()


def _matches_stored_hash(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        return False  # Not a bcrypt hash. Plain-text passwords are never accepted.


@router.post("/admin/login")
def admin_login(request: Request, payload: AdminLoginRequest):
    # Mistyped user logins land here too (the login form tries both), and people can
    # share a network, so this leaves room for typos. Production secrets are long
    # enough that guessing is hopeless regardless.
    check_rate_limit(f"admin-login:ip:{client_ip(request)}", 10, 15 * 60, "Too many login attempts. Try again in 15 minutes.")

    if not ADMIN_TOKEN or not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin access is locked until strong admin secrets are set on the server.")

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

        if admin_row and _matches_stored_hash(payload.password, str(admin_row.get("password_hash") or "")):
            return {
                "status": "success",
                "admin": {
                    "email": admin_row.get("email") or payload.email,
                    "token": ADMIN_TOKEN
                }
            }

        # Backward-compatible fallback to env credentials.
        if payload.email == ADMIN_EMAIL and hmac.compare_digest(payload.password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")):
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
        raise internal_error(e, "admin login")
