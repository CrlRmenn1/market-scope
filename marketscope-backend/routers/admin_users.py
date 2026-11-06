"""Admin user management routes."""
import psycopg2
from fastapi import APIRouter, HTTPException, Header
from psycopg2.extras import RealDictCursor

from core.database import DB_CONFIG
from core.security import verify_admin_token
from db.schema import get_users_primary_key_column
from models.requests import AdminUpdateUser
from services.user_fields import resolve_age


router = APIRouter()


def fetch_user_for_admin(cursor, user_pk_column: str, user_id: int):
    cursor.execute(
        f"""
        SELECT
            {user_pk_column} AS user_id,
            full_name,
            email,
            created_at,
            address,
            cellphone_number,
            avatar_url,
            age,
            birthday,
            primary_business,
            preferred_setup,
            first_name,
            last_name,
            street,
            barangay,
            city,
            region
        FROM users
        WHERE {user_pk_column} = %s
        """,
        (user_id,)
    )
    return cursor.fetchone()


@router.get("/admin/users")
def admin_list_users(x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        cursor.execute(
            f"""
            SELECT
                {user_pk_column} AS user_id,
                full_name,
                email,
                created_at,
                address,
                cellphone_number,
                avatar_url,
                age,
                birthday,
                primary_business,
                preferred_setup,
                first_name,
                last_name,
                street,
                barangay,
                city,
                region
            FROM users
            ORDER BY created_at DESC, {user_pk_column} DESC
            """
        )
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"status": "success", "users": users}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/admin/users/{user_id}")
def admin_update_user(user_id: int, payload: AdminUpdateUser, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        if not user_pk_column:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=500, detail="Unable to determine users primary key column")

        existing = fetch_user_for_admin(cursor, user_pk_column, user_id)
        if not existing:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        cursor.execute(
            f"""
            SELECT {user_pk_column} AS user_id
            FROM users
            WHERE email = %s AND {user_pk_column} <> %s
            """,
            (payload.email, user_id)
        )
        duplicate = cursor.fetchone()
        if duplicate:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=400, detail="Email already registered")

        # Admins edit the combined name and address. If either changes, clear
        # its split columns rather than leave them saying something different.
        new_address = payload.address or None
        name_unchanged = existing["full_name"] == payload.full_name
        address_unchanged = existing["address"] == new_address

        cursor.execute(
            f"""
            UPDATE users
            SET
                full_name = %s,
                email = %s,
                address = %s,
                cellphone_number = %s,
                avatar_url = %s,
                age = %s,
                birthday = %s,
                primary_business = %s,
                preferred_setup = %s,
                first_name = %s,
                last_name = %s,
                street = %s,
                barangay = %s,
                city = %s,
                region = %s
            WHERE {user_pk_column} = %s
            RETURNING
                {user_pk_column} AS user_id,
                full_name,
                email,
                created_at,
                address,
                cellphone_number,
                avatar_url,
                age,
                birthday,
                primary_business,
                preferred_setup,
                first_name,
                last_name,
                street,
                barangay,
                city,
                region
            """,
            (
                payload.full_name,
                payload.email,
                new_address,
                payload.cellphone_number or None,
                payload.avatar_url or None,
                resolve_age(payload.birthday, payload.age),
                payload.birthday,
                payload.primary_business or None,
                payload.preferred_setup or None,
                existing["first_name"] if name_unchanged else None,
                existing["last_name"] if name_unchanged else None,
                existing["street"] if address_unchanged else None,
                existing["barangay"] if address_unchanged else None,
                existing["city"] if address_unchanged else None,
                existing["region"] if address_unchanged else None,
                user_id
            )
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "user": updated}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        user_pk_column = get_users_primary_key_column(cursor)
        cursor.execute(
            f"DELETE FROM users WHERE {user_pk_column} = %s RETURNING {user_pk_column}",
            (user_id,)
        )
        deleted = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")

        return {"status": "success", "deleted_user_id": deleted[0]}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
