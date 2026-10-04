"""SQL for the background trend scan (tables: trend_scan_runs, trend_scan_results).

Every function takes an open RealDictCursor so the scan worker can reuse one
connection for a whole run. Get one with open_trend_cursor().

Handy queries while debugging:
    SELECT * FROM trend_scan_runs ORDER BY id DESC;
    SELECT business_type, candidate_label, viability_score
    FROM trend_scan_results ORDER BY viability_score DESC LIMIT 20;
"""
import json
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from core.database import DB_CONFIG


RUN_COLUMNS = """
    id, business_type, status, trigger_source, radius,
    candidate_count, scanned_count, started_at, finished_at, error,
    EXTRACT(EPOCH FROM (LOCALTIMESTAMP - COALESCE(finished_at, started_at)))::int AS age_seconds
"""


@contextmanager
def open_trend_cursor():
    """Autocommit connection, so every write (progress included) is visible right away."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            yield cursor
    finally:
        conn.close()


def _to_json(value):
    # Reports can carry dates (space listing verified_at/expires_at).
    return Json(value, dumps=lambda obj: json.dumps(obj, default=str))


# ---- writes (scan worker) ---------------------------------------------------

def create_run(cursor, business_type: str, trigger_source: str, radius: int) -> int:
    cursor.execute(
        """
        INSERT INTO trend_scan_runs (business_type, status, trigger_source, radius, started_at)
        VALUES (%s, 'running', %s, %s, LOCALTIMESTAMP)
        RETURNING id
        """,
        (business_type, trigger_source, radius),
    )
    return cursor.fetchone()["id"]


def set_run_candidate_count(cursor, run_id: int, candidate_count: int):
    cursor.execute(
        "UPDATE trend_scan_runs SET candidate_count = %s WHERE id = %s",
        (candidate_count, run_id),
    )


def update_run_progress(cursor, run_id: int, scanned_count: int):
    cursor.execute(
        "UPDATE trend_scan_runs SET scanned_count = %s WHERE id = %s",
        (scanned_count, run_id),
    )


def finish_run(cursor, run_id: int, status: str, error: str | None = None):
    cursor.execute(
        """
        UPDATE trend_scan_runs
        SET status = %s, error = %s, finished_at = LOCALTIMESTAMP
        WHERE id = %s
        """,
        (status, error, run_id),
    )


def insert_result(cursor, run_id: int, business_type: str, candidate: dict, report: dict):
    cursor.execute(
        """
        INSERT INTO trend_scan_results (
            run_id, business_type, candidate_source, candidate_label, space_id,
            lat, lon, viability_score, insight, report, scanned_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, LOCALTIMESTAMP)
        """,
        (
            run_id,
            business_type,
            candidate["source"],
            candidate.get("label"),
            candidate.get("space_id"),
            candidate["lat"],
            candidate["lon"],
            int(report.get("viability_score") or 0),
            report.get("insight"),
            _to_json(report),
        ),
    )


def delete_older_runs(cursor, business_type: str, keep_run_id: int):
    """Keep only the newest finished run per business (results cascade)."""
    cursor.execute(
        """
        DELETE FROM trend_scan_runs
        WHERE business_type = %s AND id <> %s AND status <> 'running'
        """,
        (business_type, keep_run_id),
    )


def mark_interrupted_runs(cursor) -> int:
    """Runs left 'running' by a previous server process can never finish."""
    cursor.execute(
        """
        UPDATE trend_scan_runs
        SET status = 'interrupted', error = 'Server restarted during the scan', finished_at = LOCALTIMESTAMP
        WHERE status = 'running'
        """
    )
    return cursor.rowcount


# ---- reads ------------------------------------------------------------------

def get_latest_run(cursor, business_type: str):
    cursor.execute(
        f"SELECT {RUN_COLUMNS} FROM trend_scan_runs WHERE business_type = %s ORDER BY id DESC LIMIT 1",
        (business_type,),
    )
    return cursor.fetchone()


def get_latest_done_run(cursor, business_type: str, radius: int):
    cursor.execute(
        f"""
        SELECT {RUN_COLUMNS}
        FROM trend_scan_runs
        WHERE business_type = %s AND status = 'done' AND radius = %s
        ORDER BY finished_at DESC
        LIMIT 1
        """,
        (business_type, radius),
    )
    return cursor.fetchone()


def fetch_run_results(cursor, run_id: int, limit: int):
    """Best-scoring spots of a run, without the heavy competitor list."""
    cursor.execute(
        """
        SELECT
            id, candidate_source, candidate_label, space_id, lat, lon,
            viability_score, insight,
            report->'breakdown' AS breakdown,
            report->'space_context' AS space_context,
            (report->>'competitors_found')::int AS competitors_found,
            (report->>'radius_meters')::int AS radius_meters
        FROM trend_scan_results
        WHERE run_id = %s
        ORDER BY viability_score DESC, id ASC
        LIMIT %s
        """,
        (run_id, limit),
    )
    return cursor.fetchall() or []


def count_run_results(cursor, run_id: int, min_score: int):
    cursor.execute(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE viability_score >= %s) AS high_chance
        FROM trend_scan_results
        WHERE run_id = %s
        """,
        (min_score, run_id),
    )
    row = cursor.fetchone() or {}
    return int(row.get("total") or 0), int(row.get("high_chance") or 0)


def fetch_result_report(cursor, result_id: int):
    cursor.execute("SELECT report FROM trend_scan_results WHERE id = %s", (result_id,))
    row = cursor.fetchone()
    return row["report"] if row else None


def fetch_latest_runs_status(cursor):
    """The newest run of every business type (debug view)."""
    cursor.execute(
        f"""
        SELECT DISTINCT ON (business_type) {RUN_COLUMNS}
        FROM trend_scan_runs
        ORDER BY business_type, id DESC
        """
    )
    return cursor.fetchall() or []
