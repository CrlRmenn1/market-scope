import json

from fastapi import HTTPException

from db.schema import (
    get_analysis_history_pk_column_async,
    get_users_primary_key_column_async,
)
from services.user_fields import (
    build_address_fields,
    build_name_fields,
    resolve_age,
    validate_avatar,
    validate_email,
    validate_text_lengths,
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


def _decode_json_column(value):
    # asyncpg returns json/jsonb columns as text (the pool sets no JSON codec).
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def normalize_history_row(row):
    for column in ("breakdown", "competitor_locations"):
        row[column] = _decode_json_column(row.get(column))

    # Scans from before engine 2.0 have none of these, and the pages say so.
    result_meta = _decode_json_column(row.pop("result_meta", None))
    if isinstance(result_meta, dict):
        row.update(result_meta)

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
                preferred_setup, onboarding_seen,
                first_name, last_name, street, barangay, city, region
            FROM users
            WHERE {user_pk_column} = $1
            """,
            user_id,
        )


async def mark_user_onboarding_seen(pool, user_id: int):
    async with pool.acquire() as conn:
        user_pk_column = await get_users_primary_key_column_async(conn)
        updated = await conn.fetchrow(
            f"""
            UPDATE users
            SET onboarding_seen = TRUE
            WHERE {user_pk_column} = $1
            RETURNING {user_pk_column} AS user_id, onboarding_seen
            """,
            user_id,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="User not found")
        return updated


async def update_user_profile(pool, user_id: int, payload):
    async with pool.acquire() as conn:
        user_pk_column = await get_users_primary_key_column_async(conn)
        existing_user = await conn.fetchrow(
            f"""
            SELECT
                {user_pk_column} AS user_id,
                email, avatar_url,
                first_name, last_name, street, barangay, city, region
            FROM users
            WHERE {user_pk_column} = $1
            """,
            user_id,
        )
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Only new values are checked, so an older photo or email saved before
        # these rules can't stop someone editing the rest of their profile.
        if payload.avatar_url != existing_user["avatar_url"]:
            validate_avatar(payload.avatar_url)
        if payload.email != existing_user["email"]:
            validate_email(payload.email)
        validate_text_lengths(payload)
        if len(payload.full_name or "") > 255:
            raise HTTPException(status_code=400, detail="Name can be at most 255 characters.")

        # A form that leaves these fields out keeps what's saved.
        if payload.first_name is not None or payload.last_name is not None:
            name_fields = build_name_fields(payload.first_name, payload.last_name)
        else:
            name_fields = {
                "full_name": payload.full_name,
                "first_name": existing_user["first_name"],
                "last_name": existing_user["last_name"],
            }

        if payload.street is None and payload.barangay is None:
            address_fields = {
                "address": payload.address or None,
                "street": existing_user["street"],
                "barangay": existing_user["barangay"],
                "city": existing_user["city"],
                "region": existing_user["region"],
            }
        else:
            address_fields = build_address_fields(payload.street, payload.barangay)
            # Both left blank on an older account: its typed address has no
            # street or barangay yet, so keep it until the user enters them.
            had_split_address = existing_user["street"] or existing_user["barangay"]
            if not address_fields["address"] and not had_split_address:
                address_fields["address"] = payload.address or None

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
                preferred_setup = $9,
                first_name = $10,
                last_name = $11,
                street = $12,
                barangay = $13,
                city = $14,
                region = $15
            WHERE {user_pk_column} = $16
            RETURNING
                {user_pk_column} AS user_id,
                full_name, email, created_at,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business,
                preferred_setup,
                first_name, last_name, street, barangay, city, region
            """,
            name_fields["full_name"],
            payload.email,
            address_fields["address"],
            payload.cellphone_number or None,
            payload.avatar_url or None,
            resolve_age(payload.birthday, payload.age),
            payload.birthday,
            payload.primary_business or None,
            payload.preferred_setup or None,
            name_fields["first_name"],
            name_fields["last_name"],
            address_fields["street"],
            address_fields["barangay"],
            address_fields["city"],
            address_fields["region"],
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
                breakdown,
                result_meta
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
                breakdown,
                result_meta
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