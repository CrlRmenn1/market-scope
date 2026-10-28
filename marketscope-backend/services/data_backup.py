"""Admin data backups: download one admin page's tables as JSON, upload to replace them.

Meant for copying the deployed data into a local database to debug against it:
download on the deployed admin panel, upload on the local one.

How an upload replaces a dataset (one transaction, rolled back on any error)
  1. Rows whose primary key is not in the file are deleted.
  2. Every row in the file is upserted by primary key.
  3. The id sequence is moved past the highest id.
Upserting instead of deleting everything keeps ON DELETE CASCADE from wiping
rows in other tables (for example a users upload keeps every kept user's
analysis history and space submissions).

Table and column names only ever come from BACKUP_DATASETS and the live
information_schema, never from the uploaded file.
"""
import base64
import datetime
import decimal

import psycopg2
from psycopg2 import errors, sql
from psycopg2.extras import Json, RealDictCursor, execute_values

from core.database import DB_CONFIG
from services.map_layers import map_layers_replaced


BACKUP_FORMAT = "marketscope-backup"
BACKUP_VERSION = 1
MAX_BACKUP_BYTES = 50 * 1024 * 1024

# Tables per admin page, parents before children.
BACKUP_DATASETS = {
    "msmes": ["custom_msme"],
    "users": ["users"],
    "spaces": ["user_space_submissions", "admin_space_submissions"],
    "map-layers": ["map_layers", "map_layer_files", "zoning_allowed_uses", "app_flags"],
}

MISSING_PARENT_MESSAGES = {
    "spaces": "Some spaces belong to users that aren't in this database. Upload the Users file first.",
}

JSON_TYPES = {"json", "jsonb"}


class DataBackupError(ValueError):
    """Bad backup file or a dataset that can't be applied (shown as a 400)."""


# ---- value encoding -------------------------------------------------------------

def encode_value(value, data_type: str):
    """A database value as JSON. BYTEA becomes base64, dates and times ISO strings."""
    if value is None:
        return None
    if data_type == "bytea":
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    return value


def decode_value(value, data_type: str):
    """The reverse of encode_value, ready to pass as a query parameter."""
    if value is None:
        return None
    if data_type == "bytea":
        try:
            return base64.b64decode(value, validate=True)
        except (TypeError, ValueError):
            raise DataBackupError("A file column in the backup is not valid base64.")
    if data_type in JSON_TYPES:
        return Json(value)
    # Postgres casts ISO date/time strings to the column type on insert.
    return value


# ---- validation -----------------------------------------------------------------

def validate_backup(dataset: str, payload) -> dict:
    """Check the file's shape against the dataset. Returns {table: {"columns", "rows"}}."""
    if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
        raise DataBackupError("This is not a MarketScope backup file.")
    if payload.get("version") != BACKUP_VERSION:
        raise DataBackupError(f"Unsupported backup version {payload.get('version')!r}.")
    if payload.get("dataset") != dataset:
        raise DataBackupError(
            f"This file holds {payload.get('dataset')!r} data, not {dataset!r}. Upload it on its own page."
        )

    tables = payload.get("tables")
    expected = BACKUP_DATASETS[dataset]
    if not isinstance(tables, dict) or set(tables) != set(expected):
        raise DataBackupError(f"The file must hold exactly these tables: {', '.join(expected)}.")

    for table in expected:
        columns = tables[table].get("columns") if isinstance(tables[table], dict) else None
        rows = tables[table].get("rows") if isinstance(tables[table], dict) else None
        if not isinstance(columns, list) or not columns or not all(isinstance(c, str) for c in columns):
            raise DataBackupError(f"Table {table} has no column list.")
        if len(set(columns)) != len(columns):
            raise DataBackupError(f"Table {table} lists a column twice.")
        if not isinstance(rows, list) or not all(isinstance(r, list) and len(r) == len(columns) for r in rows):
            raise DataBackupError(f"Table {table} has rows that don't match its columns.")
    return tables


def check_columns(table: str, file_columns: list, live_types: dict, primary_key: str):
    """Every column in the file must exist in the live table, and the primary key must be there."""
    unknown = [c for c in file_columns if c not in live_types]
    if unknown:
        raise DataBackupError(
            f"Table {table} in the file has columns this database doesn't: {', '.join(unknown)}. "
            "Update this backend and restart it so it adds them."
        )
    if primary_key not in file_columns:
        raise DataBackupError(f"Table {table} in the file is missing its primary key {primary_key}.")


# ---- database helpers ------------------------------------------------------------

def _connect():
    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor() as cursor:
        # DB_CONFIG caps statements at 10 s; big layers over a remote link take longer.
        cursor.execute("SET statement_timeout = 0")
    return conn


def _live_column_types(cursor, table: str) -> dict:
    cursor.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    types = {row["column_name"]: row["data_type"] for row in cursor.fetchall()}
    if not types:
        raise DataBackupError(f"Table {table} doesn't exist in this database. Start the backend once to create it.")
    return types


def _primary_key(cursor, table: str) -> str:
    cursor.execute(
        """
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = %s::regclass AND i.indisprimary
        """,
        (f"public.{table}",),
    )
    rows = cursor.fetchall()
    if len(rows) != 1:
        raise DataBackupError(f"Table {table} needs a single-column primary key.")
    return rows[0]["attname"]


def _reset_sequence(cursor, table: str, primary_key: str):
    cursor.execute("SELECT pg_get_serial_sequence(%s, %s) AS seq", (f"public.{table}", primary_key))
    sequence = cursor.fetchone()["seq"]
    if not sequence:
        return
    cursor.execute(
        sql.SQL("SELECT setval(%s, COALESCE(MAX({pk}), 1), MAX({pk}) IS NOT NULL) FROM {table}").format(
            pk=sql.Identifier(primary_key), table=sql.Identifier(table)
        ),
        (sequence,),
    )


# ---- export / import --------------------------------------------------------------

def export_dataset(dataset: str) -> dict:
    tables = {}
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            for table in BACKUP_DATASETS[dataset]:
                types = _live_column_types(cursor, table)
                primary_key = _primary_key(cursor, table)
                columns = list(types)
                cursor.execute(
                    sql.SQL("SELECT {cols} FROM {table} ORDER BY {pk}").format(
                        cols=sql.SQL(", ").join(map(sql.Identifier, columns)),
                        table=sql.Identifier(table),
                        pk=sql.Identifier(primary_key),
                    )
                )
                rows = [[encode_value(row[c], types[c]) for c in columns] for row in cursor.fetchall()]
                tables[table] = {"columns": columns, "rows": rows}
    finally:
        conn.close()

    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "dataset": dataset,
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_host": DB_CONFIG.get("host"),
        "tables": tables,
    }


def _replace_table(cursor, table: str, columns: list, rows: list) -> dict:
    types = _live_column_types(cursor, table)
    primary_key = _primary_key(cursor, table)
    check_columns(table, columns, types, primary_key)

    pk_index = columns.index(primary_key)
    keys = [row[pk_index] for row in rows]
    table_id, pk_id = sql.Identifier(table), sql.Identifier(primary_key)

    cursor.execute(sql.SQL("DELETE FROM {t} WHERE NOT ({pk} = ANY(%s))").format(t=table_id, pk=pk_id), (keys,))
    deleted = cursor.rowcount

    if table == "map_layers":
        # Only one active layer per category is allowed, even halfway through the upsert.
        cursor.execute("UPDATE map_layers SET is_active = FALSE WHERE is_active")

    if rows:
        updates = [c for c in columns if c != primary_key]
        conflict_action = (
            sql.SQL("DO UPDATE SET ") + sql.SQL(", ").join(
                sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in updates
            )
            if updates else sql.SQL("DO NOTHING")
        )
        query = sql.SQL("INSERT INTO {t} ({cols}) VALUES %s ON CONFLICT ({pk}) {action}").format(
            t=table_id,
            cols=sql.SQL(", ").join(map(sql.Identifier, columns)),
            pk=pk_id,
            action=conflict_action,
        )
        values = [[decode_value(v, types[c]) for v, c in zip(row, columns)] for row in rows]
        execute_values(cursor, query.as_string(cursor), values, page_size=200)

    _reset_sequence(cursor, table, primary_key)
    return {"rows": len(rows), "removed": deleted}


def import_dataset(dataset: str, payload) -> dict:
    tables = validate_backup(dataset, payload)
    summary = {}
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            for table in BACKUP_DATASETS[dataset]:
                summary[table] = _replace_table(cursor, table, tables[table]["columns"], tables[table]["rows"])
        conn.commit()
    except errors.ForeignKeyViolation:
        conn.rollback()
        raise DataBackupError(
            MISSING_PARENT_MESSAGES.get(dataset, "Some rows point at records that aren't in this database.")
        )
    except (errors.UniqueViolation, errors.CheckViolation, errors.NotNullViolation, errors.DataError) as exc:
        conn.rollback()
        raise DataBackupError(f"The file doesn't fit this database: {exc.diag.message_primary}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if dataset == "map-layers":
        map_layers_replaced()
    return summary
