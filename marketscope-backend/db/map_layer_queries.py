"""SQL for admin map layers (tables: map_layers, map_layer_files, app_flags).

Every function takes an open RealDictCursor. Get one with open_map_layer_cursor(),
which commits when the block finishes and rolls back if it raises.

Handy queries while debugging:
    SELECT id, category, name, origin, is_active, jsonb_array_length(geojson->'features') FROM map_layers;
    SELECT * FROM app_flags;
"""
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from core.database import DB_CONFIG


LAYER_COLUMNS = """
    l.id, l.category, l.name, l.source_note, l.origin, l.is_active, l.created_at, l.updated_at,
    COALESCE(jsonb_array_length(l.geojson->'features'), 0) AS feature_count
"""


LAYER_FILES_COLUMN = """
    COALESCE((
        SELECT json_agg(json_build_object(
            'id', f.id, 'filename', f.filename, 'size_bytes', f.size_bytes, 'uploaded_at', f.uploaded_at
        ) ORDER BY f.id)
        FROM map_layer_files f WHERE f.layer_id = l.id
    ), '[]'::json) AS files
"""


@contextmanager
def open_map_layer_cursor():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---- layers -----------------------------------------------------------------

def list_layers(cursor, category: str | None = None):
    query = f"SELECT {LAYER_COLUMNS}, {LAYER_FILES_COLUMN} FROM map_layers l"
    params = []
    if category:
        query += " WHERE l.category = %s"
        params.append(category)
    query += " ORDER BY l.is_active DESC, l.updated_at DESC, l.id DESC"
    cursor.execute(query, params)
    return cursor.fetchall()


def get_layer(cursor, layer_id: int):
    cursor.execute(
        f"SELECT {LAYER_COLUMNS}, {LAYER_FILES_COLUMN}, l.geojson FROM map_layers l WHERE l.id = %s",
        (layer_id,),
    )
    return cursor.fetchone()


def get_active_layer(cursor, category: str):
    cursor.execute(
        f"SELECT {LAYER_COLUMNS}, l.geojson FROM map_layers l WHERE l.category = %s AND l.is_active",
        (category,),
    )
    return cursor.fetchone()


def insert_layer(cursor, category: str, name: str, source_note: str | None, origin: str, geojson: dict, is_active: bool = False):
    if is_active:
        cursor.execute("UPDATE map_layers SET is_active = FALSE WHERE category = %s AND is_active", (category,))
    cursor.execute(
        """
        INSERT INTO map_layers (category, name, source_note, origin, geojson, is_active)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (category, name, source_note, origin, Json(geojson), is_active),
    )
    return cursor.fetchone()["id"]


def update_layer(cursor, layer_id: int, name: str, source_note: str | None, geojson: dict):
    cursor.execute(
        """
        UPDATE map_layers
        SET name = %s, source_note = %s, geojson = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        RETURNING id
        """,
        (name, source_note, Json(geojson), layer_id),
    )
    return cursor.fetchone()


def list_layer_stacks(cursor):
    """id, category and geojson of every layer (for one-time data migrations)."""
    cursor.execute("SELECT id, category, geojson FROM map_layers ORDER BY id")
    return cursor.fetchall()


def set_layer_geojson(cursor, layer_id: int, geojson: dict):
    """Rewrite a layer's shapes without touching updated_at (migrations only)."""
    cursor.execute("UPDATE map_layers SET geojson = %s WHERE id = %s", (Json(geojson), layer_id))


def set_layer_active(cursor, layer_id: int, is_active: bool):
    """Activating a layer deactivates the other layers in its category."""
    cursor.execute("SELECT id, category FROM map_layers WHERE id = %s", (layer_id,))
    layer = cursor.fetchone()
    if not layer:
        return None
    if is_active:
        cursor.execute(
            "UPDATE map_layers SET is_active = FALSE WHERE category = %s AND is_active AND id <> %s",
            (layer["category"], layer_id),
        )
    cursor.execute(
        "UPDATE map_layers SET is_active = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
        (is_active, layer_id),
    )
    return layer


def delete_layer(cursor, layer_id: int):
    cursor.execute("DELETE FROM map_layers WHERE id = %s RETURNING id, category, is_active", (layer_id,))
    return cursor.fetchone()


# ---- original files -----------------------------------------------------------

def insert_layer_file(cursor, layer_id: int, filename: str, content_type: str | None, data: bytes):
    cursor.execute(
        """
        INSERT INTO map_layer_files (layer_id, filename, content_type, size_bytes, data)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (layer_id, filename, content_type, len(data), psycopg2.Binary(data)),
    )
    return cursor.fetchone()["id"]


def get_layer_file(cursor, layer_id: int, file_id: int):
    cursor.execute(
        "SELECT filename, content_type, data FROM map_layer_files WHERE id = %s AND layer_id = %s",
        (file_id, layer_id),
    )
    return cursor.fetchone()


# ---- zoning allowed uses ----------------------------------------------------------

def list_zoning_allowed_uses(cursor):
    cursor.execute("SELECT zone_class, business_type FROM zoning_allowed_uses ORDER BY zone_class, business_type")
    return cursor.fetchall()


def replace_zoning_allowed_uses(cursor, pairs):
    """Replace the whole table with (zone_class, business_type) pairs."""
    cursor.execute("DELETE FROM zoning_allowed_uses")
    for zone_class, business_type in pairs:
        cursor.execute(
            "INSERT INTO zoning_allowed_uses (zone_class, business_type) VALUES (%s, %s)",
            (zone_class, business_type),
        )


# ---- flags --------------------------------------------------------------------

def get_flag(cursor, key: str):
    cursor.execute("SELECT key, value, set_at FROM app_flags WHERE key = %s", (key,))
    return cursor.fetchone()


def set_flag(cursor, key: str, value: str | None = None):
    cursor.execute(
        """
        INSERT INTO app_flags (key, value, set_at) VALUES (%s, %s, LOCALTIMESTAMP)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, set_at = EXCLUDED.set_at
        RETURNING set_at
        """,
        (key, value),
    )
    return cursor.fetchone()["set_at"]
