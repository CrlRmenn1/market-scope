import bcrypt

from fastapi import HTTPException
from datetime import datetime, timezone

from db_schema import (
    generate_reset_code,
    get_analysis_history_pk_column_async,
    get_users_primary_key_column_async,
    send_password_reset_email,
)


async def register_user(pool, payload):
    async with pool.acquire() as conn:
        user_pk_column = await get_users_primary_key_column_async(conn)
        existing_user = await conn.fetchrow(
            f"SELECT {user_pk_column} FROM users WHERE email = $1",
            payload.email,
        )
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_password = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        new_user = await conn.fetchrow(
            f"""
            INSERT INTO users (
                full_name, email, password_hash,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business,
                startup_capital, risk_tolerance, preferred_setup,
                time_commitment, target_payback_months
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING
                {user_pk_column}, full_name, email, created_at,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business,
                startup_capital, risk_tolerance, preferred_setup,
                time_commitment, target_payback_months
            """,
            payload.full_name,
            payload.email,
            hashed_password,
            payload.address or None,
            payload.cellphone_number or None,
            payload.avatar_url or None,
            payload.age,
            payload.birthday,
            payload.primary_business or None,
            payload.startup_capital,
            payload.risk_tolerance or None,
            payload.preferred_setup or None,
            payload.time_commitment or None,
            payload.target_payback_months,
        )

    return {
        "status": "success",
        "user": {
            "id": new_user[0],
            "user_id": new_user[0],
            "name": new_user[1],
            "email": new_user[2],
            "created_at": new_user[3],
            "address": new_user[4],
            "cellphone_number": new_user[5],
            "avatar_url": new_user[6],
            "age": new_user[7],
            "birthday": new_user[8],
            "primary_business": new_user[9],
            "startup_capital": new_user[10],
            "risk_tolerance": new_user[11],
            "preferred_setup": new_user[12],
            "time_commitment": new_user[13],
            "target_payback_months": new_user[14],
        },
    }


async def login_user(pool, payload):
    async with pool.acquire() as conn:
        user_pk_column = await get_users_primary_key_column_async(conn)
        row = await conn.fetchrow(
            f"""
            SELECT
                {user_pk_column} AS user_id,
                full_name, email, password_hash, created_at,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business,
                startup_capital, risk_tolerance, preferred_setup,
                time_commitment, target_payback_months
            FROM users
            WHERE email = $1
            """,
            payload.email,
        )

    db_user = dict(row) if row else None
    if not db_user or not bcrypt.checkpw(payload.password.encode("utf-8"), db_user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {
        "status": "success",
        "user": {
            "id": db_user["user_id"],
            "user_id": db_user["user_id"],
            "name": db_user["full_name"],
            "email": db_user["email"],
            "created_at": db_user["created_at"],
            "address": db_user.get("address"),
            "cellphone_number": db_user.get("cellphone_number"),
            "avatar_url": db_user.get("avatar_url"),
            "age": db_user.get("age"),
            "birthday": db_user.get("birthday"),
            "primary_business": db_user.get("primary_business"),
            "startup_capital": db_user.get("startup_capital"),
            "risk_tolerance": db_user.get("risk_tolerance"),
            "preferred_setup": db_user.get("preferred_setup"),
            "time_commitment": db_user.get("time_commitment"),
            "target_payback_months": db_user.get("target_payback_months"),
        },
    }


async def forgot_password(pool, payload, ttl_minutes):
    async with pool.acquire() as conn:
        user_pk_column = await get_users_primary_key_column_async(conn)
        db_user = await conn.fetchrow(
            f"SELECT {user_pk_column} AS user_id, email FROM users WHERE email = $1",
            payload.email,
        )

        if not db_user:
            return {
                "status": "success",
                "detail": "If your account exists, a reset code has been sent to your email.",
            }

        user_id = db_user["user_id"]
        reset_code = generate_reset_code()
        reset_code_hash = bcrypt.hashpw(reset_code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        async with conn.transaction():
            await conn.execute(
                """
                UPDATE password_reset_codes
                SET used_at = CURRENT_TIMESTAMP
                WHERE user_id = $1 AND used_at IS NULL
                """,
                user_id,
            )
            await conn.execute(
                """
                INSERT INTO password_reset_codes (user_id, code_hash, expires_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP + ($3 || ' minutes')::interval)
                """,
                user_id,
                reset_code_hash,
                ttl_minutes,
            )

        send_password_reset_email(payload.email, reset_code)

        response = {
            "status": "success",
            "detail": "If your account exists, a reset code has been sent to your email.",
        }
        return response


async def reset_password(pool, payload):
    if len(payload.new_password.strip()) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    async with pool.acquire() as conn:
        user_pk_column = await get_users_primary_key_column_async(conn)
        db_user = await conn.fetchrow(
            f"SELECT {user_pk_column} AS user_id FROM users WHERE email = $1",
            payload.email,
        )
        if not db_user:
            raise HTTPException(status_code=400, detail="Invalid reset request")

        reset_row = await conn.fetchrow(
            """
            SELECT id, code_hash, expires_at
            FROM password_reset_codes
            WHERE user_id = $1 AND used_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            db_user["user_id"],
        )
        if not reset_row:
            raise HTTPException(status_code=400, detail="No active reset code found")

        expires_at = reset_row["expires_at"]
        if isinstance(expires_at, datetime) and expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(status_code=400, detail="Reset code expired. Request a new one.")

        is_valid_code = bcrypt.checkpw(payload.code.encode("utf-8"), reset_row["code_hash"].encode("utf-8"))
        if not is_valid_code:
            raise HTTPException(status_code=400, detail="Invalid reset code")

        new_hash = bcrypt.hashpw(payload.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        async with conn.transaction():
            await conn.execute(
                f"UPDATE users SET password_hash = $1 WHERE {user_pk_column} = $2",
                new_hash,
                db_user["user_id"],
            )
            await conn.execute(
                "UPDATE password_reset_codes SET used_at = CURRENT_TIMESTAMP WHERE id = $1",
                reset_row["id"],
            )

    return {"status": "success", "detail": "Password reset successful. You can now log in."}


async def reset_password_direct(pool, payload):
    if len(payload.new_password.strip()) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    async with pool.acquire() as conn:
        user_pk_column = await get_users_primary_key_column_async(conn)
        db_user = await conn.fetchrow(
            f"SELECT {user_pk_column} AS user_id FROM users WHERE email = $1",
            payload.email,
        )
        if not db_user:
            raise HTTPException(status_code=404, detail="Email not found")

        new_hash = bcrypt.hashpw(payload.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        await conn.execute(
            f"UPDATE users SET password_hash = $1 WHERE {user_pk_column} = $2",
            new_hash,
            db_user["user_id"],
        )

    return {"status": "success", "detail": "Password reset successful. You can now log in."}