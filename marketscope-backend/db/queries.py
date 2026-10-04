"""Read-only database lookups shared by several routes and services."""
import psycopg2
from psycopg2.extras import RealDictCursor

from constants.msme import VERIFIED_LOCAL_FEATURE_KINDS
from core.database import DB_CONFIG
from db.schema import ensure_verified_local_features_table
from utils.values import normalize_osm_value


def fetch_verified_local_features(feature_kind=None, business_type=None, active_only=True, cursor=None):
    # When a cursor is supplied, the caller owns the connection (and is
    # responsible for having already ensured the table exists) - this lets
    # callers that need several of these in a row (e.g.
    # evaluate_layered_market_context) share one connection instead of each
    # call opening/closing its own. Callers that don't pass one get today's
    # exact behavior, unchanged.
    owns_connection = cursor is None
    conn = None
    try:
        if owns_connection:
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
            if normalized_kind in VERIFIED_LOCAL_FEATURE_KINDS:
                query.append("AND feature_kind = %s")
                params.append(normalized_kind)

        if business_type:
            query.append("AND LOWER(TRIM(COALESCE(business_type, ''))) = %s")
            params.append(normalize_osm_value(business_type))

        if active_only:
            query.append("AND is_active = TRUE")

        query.append("ORDER BY updated_at DESC, created_at DESC, id DESC")
        cursor.execute("\n".join(query), params)
        rows = cursor.fetchall()
        if conn is not None:
            cursor.close()
            conn.close()
        return rows
    except Exception as e:
        print(f"Verified local feature fetch error: {e}")
        return []


def fetch_custom_msmes(business_key, cursor=None):
    conn = None
    try:
        if cursor is None:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT name, latitude, longitude FROM custom_msme WHERE business_type = %s", (business_key,))
        results = cursor.fetchall()
        if conn is not None:
            cursor.close()
            conn.close()
        return results
    except Exception as e:
        print(f"Database Error: {e}")
        return []


def fetch_custom_msme_counts(cursor):
    cursor.execute(
        """
        SELECT
            LOWER(TRIM(business_type)) AS business_key,
            COUNT(*) AS total
        FROM custom_msme
        GROUP BY LOWER(TRIM(business_type))
        """
    )

    rows = cursor.fetchall() or []
    counts = {}
    for row in rows:
        business_key = str(row.get("business_key") or "").strip()
        if not business_key:
            continue
        counts[business_key] = int(row.get("total") or 0)

    return counts


def fetch_user_profile_by_id(cursor, user_pk_column: str, user_id: int):
    cursor.execute(
        f"""
        SELECT
            {user_pk_column} AS user_id,
            full_name,
            email,
            address,
            cellphone_number,
            avatar_url,
            age,
            birthday,
            primary_business,
            startup_capital,
            preferred_setup,
            target_payback_months,
            created_at
        FROM users
        WHERE {user_pk_column} = %s
        LIMIT 1
        """,
        (user_id,)
    )
    return cursor.fetchone()


async def fetch_user_profile_by_id_async(conn, user_pk_column: str, user_id: int):
    row = await conn.fetchrow(
        f"""
        SELECT
            {user_pk_column} AS user_id,
            full_name,
            email,
            address,
            cellphone_number,
            avatar_url,
            age,
            birthday,
            primary_business,
            startup_capital,
            preferred_setup,
            target_payback_months,
            created_at
        FROM users
        WHERE {user_pk_column} = $1
        LIMIT 1
        """,
        user_id,
    )
    return dict(row) if row else None
