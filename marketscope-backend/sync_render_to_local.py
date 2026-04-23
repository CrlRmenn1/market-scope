import os
import sys
import traceback
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.extras import Json

LOCAL_DB_CONFIG = {
    "dbname": os.environ.get("MARKETSCOPE_DB_NAME", "marketscope_db"),
    "user": os.environ.get("MARKETSCOPE_DB_USER", "postgres"),
    "password": os.environ.get("MARKETSCOPE_DB_PASSWORD", "1234"),
    "host": os.environ.get("MARKETSCOPE_DB_HOST", "localhost"),
    "port": os.environ.get("MARKETSCOPE_DB_PORT", "5432"),
}

TABLE_COPY_ORDER = [
    "users",
    "admin_users",
    "custom_msme",
    "analysis_history",
    "password_reset_codes",
    "admin_space_submissions",
    "user_space_submissions",
]


def parse_source_db_config(raw_url: str):
    parsed = urlparse(raw_url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ValueError("Source URL must start with postgres:// or postgresql://")

    return {
        "dbname": parsed.path.lstrip("/") or "postgres",
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname,
        "port": str(parsed.port or 5432),
        "sslmode": os.environ.get("RENDER_DB_SSLMODE", "require"),
    }


def list_tables(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return {row[0] for row in cur.fetchall()}


def list_columns(conn, table_name):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        return [row[0] for row in cur.fetchall()]


def reset_sequences(conn, tables):
    with conn.cursor() as cur:
        for table_name in tables:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                                    AND column_default LIKE 'nextval(%%'
                ORDER BY ordinal_position
                """,
                (table_name,),
            )
            serial_columns = [row[0] for row in cur.fetchall()]
            for column_name in serial_columns:
                cur.execute(
                    """
                    SELECT pg_get_serial_sequence(%s, %s)
                    """,
                    (f"public.{table_name}", column_name),
                )
                seq_row = cur.fetchone()
                sequence_name = seq_row[0] if seq_row and len(seq_row) > 0 else None
                if not sequence_name:
                    continue

                cur.execute(f"SELECT COALESCE(MAX({column_name}), 0) FROM {table_name}")
                max_id = cur.fetchone()[0]
                is_called = max_id > 0
                cur.execute("SELECT setval(%s, %s, %s)", (sequence_name, max_id, is_called))


def copy_table_data(source_conn, target_conn, table_name):
    source_columns = list_columns(source_conn, table_name)
    target_columns = list_columns(target_conn, table_name)
    common_columns = [col for col in target_columns if col in source_columns]

    if not common_columns:
        return 0, "no-common-columns"

    select_sql = f"SELECT {', '.join(common_columns)} FROM {table_name}"
    insert_sql = f"INSERT INTO {table_name} ({', '.join(common_columns)}) VALUES %s"

    rows_copied = 0

    def normalize_value(value):
        if isinstance(value, (dict, list)):
            return Json(value)
        return value

    with source_conn.cursor(cursor_factory=RealDictCursor) as source_cur:
        source_cur.itersize = 1000
        source_cur.execute(select_sql)

        while True:
            batch = source_cur.fetchmany(1000)
            if not batch:
                break

            values = [tuple(normalize_value(row[col]) for col in common_columns) for row in batch]
            with target_conn.cursor() as target_cur:
                execute_values(target_cur, insert_sql, values, page_size=1000)
            rows_copied += len(values)

    return rows_copied, "ok"


def main():
    source_url = os.environ.get("RENDER_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if len(sys.argv) > 1:
        source_url = sys.argv[1].strip()

    if not source_url:
        print("ERROR: Missing source database URL.")
        print("Set RENDER_DATABASE_URL or pass URL as first argument.")
        sys.exit(1)

    source_config = parse_source_db_config(source_url)

    print("Connecting to source (Render) database...")
    source_conn = psycopg2.connect(**source_config)
    print("Connecting to target (localhost) database...")
    target_conn = psycopg2.connect(**LOCAL_DB_CONFIG)

    source_conn.autocommit = False
    target_conn.autocommit = False

    try:
        source_tables = list_tables(source_conn)
        target_tables = list_tables(target_conn)

        tables_to_copy = [
            table_name
            for table_name in TABLE_COPY_ORDER
            if table_name in source_tables and table_name in target_tables
        ]

        if not tables_to_copy:
            raise RuntimeError("No matching tables found between source and target")

        print("Truncating target tables...")
        with target_conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE " + ", ".join(tables_to_copy) + " RESTART IDENTITY CASCADE"
            )

        print("Copying rows...")
        for table_name in tables_to_copy:
            count, status = copy_table_data(source_conn, target_conn, table_name)
            print(f"- {table_name}: {count} rows ({status})")

        reset_sequences(target_conn, tables_to_copy)

        target_conn.commit()
        source_conn.commit()
        print("DONE: Render data copied into localhost database.")
    except Exception as exc:
        target_conn.rollback()
        source_conn.rollback()
        print(f"ERROR: {exc}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        source_conn.close()
        target_conn.close()


if __name__ == "__main__":
    main()
