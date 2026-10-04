"""Commercial space markers and matching a coordinate to a nearby space."""
import psycopg2
from psycopg2.extras import RealDictCursor

from core.database import DB_CONFIG
from db.schema import (
    ensure_admin_space_submissions_table,
    ensure_user_space_submissions_table,
    get_users_primary_key_column,
)
from utils.geo import calculate_distance
from utils.values import to_finite_number


def fetch_active_space_markers_for_analysis():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    user_pk_column = get_users_primary_key_column(cursor)
    ensure_user_space_submissions_table(cursor, user_pk_column)
    ensure_admin_space_submissions_table(cursor)

    cursor.execute(
        """
        SELECT
            id,
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
            status,
            created_at,
            reviewed_at,
            'user'::text AS source_type
        FROM user_space_submissions
        WHERE status IN ('approved', 'pending')
        """
    )
    user_rows = cursor.fetchall() or []

    cursor.execute(
        """
        SELECT
            id,
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
            confidence_score,
            photo_urls,
            created_at,
            verified_at,
            expires_at,
            'admin'::text AS source_type
        FROM admin_space_submissions
        WHERE is_active = TRUE
          AND (expires_at IS NULL OR expires_at >= CURRENT_DATE)
        """
    )
    admin_rows = cursor.fetchall() or []

    cursor.close()
    conn.close()

    markers = []

    for row in user_rows:
        markers.append({
            "id": f"user-{row.get('id')}",
            "source_type": "user",
            "title": row.get("title"),
            "listing_mode": row.get("listing_mode"),
            "guarantee_level": "guaranteed",
            "status": row.get("status"),
            "property_type": row.get("property_type"),
            "business_type": row.get("business_type"),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "address_text": row.get("address_text"),
            "price_min": row.get("price_min"),
            "price_max": row.get("price_max"),
            "contact_info": row.get("contact_info"),
            "notes": row.get("notes"),
            "photo_urls": row.get("photo_urls") or [],
            "confidence_score": 100,
            "verified_at": row.get("reviewed_at") or row.get("created_at"),
            "expires_at": None,
        })

    for row in admin_rows:
        markers.append({
            "id": f"admin-{row.get('id')}",
            "source_type": "admin",
            "title": row.get("title"),
            "listing_mode": row.get("listing_mode"),
            "guarantee_level": row.get("guarantee_level") or "potential",
            "property_type": row.get("property_type"),
            "business_type": row.get("business_type"),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "address_text": row.get("address_text"),
            "price_min": row.get("price_min"),
            "price_max": row.get("price_max"),
            "contact_info": row.get("contact_info"),
            "notes": row.get("notes"),
            "photo_urls": row.get("photo_urls") or [],
            "confidence_score": row.get("confidence_score"),
            "verified_at": row.get("verified_at") or row.get("created_at"),
            "expires_at": row.get("expires_at"),
        })

    return markers


def resolve_space_context_for_coords(lat: float, lon: float, space_markers=None, max_distance_meters: int = 85):
    markers = space_markers if isinstance(space_markers, list) else fetch_active_space_markers_for_analysis()
    best_match = None
    best_distance = None

    for marker in markers:
        marker_lat = to_finite_number(marker.get("latitude"))
        marker_lon = to_finite_number(marker.get("longitude"))
        if marker_lat is None or marker_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, marker_lat, marker_lon)
        if distance_m > max_distance_meters:
            continue

        if best_distance is None or distance_m < best_distance:
            best_distance = distance_m
            best_match = marker

    if not best_match:
        return None

    return {
        "id": best_match.get("id"),
        "source_type": best_match.get("source_type"),
        "title": best_match.get("title"),
        "listing_mode": best_match.get("listing_mode"),
        "guarantee_level": best_match.get("guarantee_level"),
        "property_type": best_match.get("property_type"),
        "business_type": best_match.get("business_type"),
        "latitude": best_match.get("latitude"),
        "longitude": best_match.get("longitude"),
        "address_text": best_match.get("address_text"),
        "price_min": best_match.get("price_min"),
        "price_max": best_match.get("price_max"),
        "contact_info": best_match.get("contact_info"),
        "notes": best_match.get("notes"),
        "confidence_score": best_match.get("confidence_score"),
        "verified_at": best_match.get("verified_at"),
        "expires_at": best_match.get("expires_at"),
        "distance_meters": int(round(best_distance if best_distance is not None else 0.0)),
    }
