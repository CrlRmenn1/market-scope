from fastapi import HTTPException

from db_schema import (
    get_analysis_history_pk_column_async,
    get_users_primary_key_column_async,
)


def saturation_score_from_competitors(competitor_count):
    if competitor_count <= 0:
        return 25
    if competitor_count == 1:
        return 20
    if competitor_count <= 3:
        return 15
    if competitor_count <= 5:
        return 10
    return 5


def build_legacy_breakdown(row):
    competitors_found = row.get("competitors_found") or 0
    total_score = row.get("viability_score") or 0
    saturation_score = saturation_score_from_competitors(competitors_found)

    remainder = max(0, total_score - saturation_score)
    base_split = int(remainder / 3)
    extra = remainder - (base_split * 3)
    zoning_score = min(25, base_split + (1 if extra > 0 else 0))
    hazard_score = min(25, base_split + (1 if extra > 1 else 0))
    demand_score = min(25, base_split)

    legacy_note = "Estimated for legacy record. Run a fresh analysis to store exact factor-level values."
    return {
        "zoning": {
            "score": zoning_score,
            "status": "Legacy Estimate",
            "note": legacy_note,
        },
        "hazard": {
            "score": hazard_score,
            "status": "Legacy Estimate",
            "note": legacy_note,
        },
        "demand": {
            "score": demand_score,
            "status": "Legacy Estimate",
            "note": legacy_note,
        },
        "saturation": {
            "score": saturation_score,
            "status": "Legacy Estimate",
            "note": legacy_note,
        },
    }


def normalize_history_row(row):
    if row.get("competitors_found") is None:
        competitor_locations = row.get("competitor_locations") or []
        if isinstance(competitor_locations, list):
            row["competitors_found"] = len(competitor_locations)
        else:
            row["competitors_found"] = 0

    if row.get("target_lng") is None and row.get("target_lon") is not None:
        row["target_lng"] = row.get("target_lon")
    if row.get("radius_meters") is None:
        row["radius_meters"] = 340

    competitors_found = int(row.get("competitors_found") or 0)
    if competitors_found <= 0:
        row["competitor_locations"] = []

    breakdown = row.get("breakdown")
    if not isinstance(breakdown, dict) or not breakdown:
        row["breakdown"] = build_legacy_breakdown(row)

    return row


async def get_user_profile(pool, user_id: int):
    async with pool.acquire() as conn:
        user_pk_column = await get_users_primary_key_column_async(conn)
        return await conn.fetchrow(
            f"""
            SELECT
                {user_pk_column} AS user_id,
                full_name, email, created_at,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business,
                startup_capital, risk_tolerance, preferred_setup,
                time_commitment, target_payback_months
            FROM users
            WHERE {user_pk_column} = $1
            """,
            user_id,
        )


async def update_user_profile(pool, user_id: int, payload):
    async with pool.acquire() as conn:
        user_pk_column = await get_users_primary_key_column_async(conn)
        existing_user = await conn.fetchrow(
            f"SELECT {user_pk_column} AS user_id FROM users WHERE {user_pk_column} = $1",
            user_id,
        )
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")

        duplicate_email = await conn.fetchrow(
            f"""
            SELECT {user_pk_column} AS user_id
            FROM users
            WHERE email = $1 AND {user_pk_column} <> $2
            """,
            payload.email,
            user_id,
        )
        if duplicate_email:
            raise HTTPException(status_code=400, detail="Email already registered")

        return await conn.fetchrow(
            f"""
            UPDATE users
            SET
                full_name = $1,
                email = $2,
                address = $3,
                cellphone_number = $4,
                avatar_url = $5,
                age = $6,
                birthday = $7,
                primary_business = $8,
                startup_capital = $9,
                risk_tolerance = $10,
                preferred_setup = $11,
                time_commitment = $12,
                target_payback_months = $13
            WHERE {user_pk_column} = $14
            RETURNING
                {user_pk_column} AS user_id,
                full_name, email, created_at,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business,
                startup_capital, risk_tolerance, preferred_setup,
                time_commitment, target_payback_months
            """,
            payload.full_name,
            payload.email,
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
            user_id,
        )


async def get_user_history(pool, user_id: int):
    async with pool.acquire() as conn:
        history_pk_column = await get_analysis_history_pk_column_async(conn)
        rows = await conn.fetch(
            f"""
            SELECT
                {history_pk_column} AS history_id,
                business_type,
                viability_score,
                target_lat,
                target_lon AS target_lng,
                radius_used AS radius_meters,
                insight,
                COALESCE(
                    competitors_found,
                    CASE
                        WHEN competitor_locations IS NOT NULL THEN jsonb_array_length(competitor_locations)
                        ELSE 0
                    END,
                    0
                ) AS competitors_found,
                competitor_locations,
                scan_date AS created_at,
                breakdown
            FROM analysis_history
            WHERE user_id = $1
            ORDER BY scan_date DESC, {history_pk_column} DESC
            """,
            user_id,
        )
        return [normalize_history_row(dict(row)) for row in rows]


async def get_user_history_item(pool, user_id: int, history_id: int):
    async with pool.acquire() as conn:
        history_pk_column = await get_analysis_history_pk_column_async(conn)
        row = await conn.fetchrow(
            f"""
            SELECT
                {history_pk_column} AS history_id,
                business_type,
                viability_score,
                target_lat,
                target_lon AS target_lng,
                radius_used AS radius_meters,
                insight,
                COALESCE(
                    competitors_found,
                    CASE
                        WHEN competitor_locations IS NOT NULL THEN jsonb_array_length(competitor_locations)
                        ELSE 0
                    END,
                    0
                ) AS competitors_found,
                competitor_locations,
                scan_date AS created_at,
                breakdown
            FROM analysis_history
            WHERE user_id = $1 AND {history_pk_column} = $2
            LIMIT 1
            """,
            user_id,
            history_id,
        )
        return normalize_history_row(dict(row)) if row else None


async def delete_user_history_item(pool, user_id: int, history_id: int):
    async with pool.acquire() as conn:
        history_pk_column = await get_analysis_history_pk_column_async(conn)
        return await conn.fetchrow(
            f"DELETE FROM analysis_history WHERE user_id = $1 AND {history_pk_column} = $2 RETURNING {history_pk_column}",
            user_id,
            history_id,
        )