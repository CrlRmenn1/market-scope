"""
In-memory cache of the AHP weight configs (ahp_weight_configs table), keyed by
(level, category). Avoids a DB round-trip per perform_analysis() call, since
background trend scans call perform_analysis() many times per scan. Loaded
once at startup (lifespan). The weights are the seeded AHP matrices from
db/schema.py; there is no admin editor, so change them in the table directly.
"""
from threading import Lock

import psycopg2
from psycopg2.extras import RealDictCursor

from core.database import DB_CONFIG
from db.schema import AHP_GLOBAL_CATEGORY_SENTINEL


_AHP_WEIGHTS_CACHE = {}


_AHP_WEIGHTS_CACHE_LOCK = Lock()


def _load_ahp_weights_cache():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            SELECT level, category, criteria_labels, pairwise_matrix, priority_vector,
                   lambda_max, consistency_index, random_index, consistency_ratio,
                   is_consistent, updated_by_admin_email, updated_at
            FROM ahp_weight_configs
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[AHP] Failed to load weights cache: {e}", flush=True)
        return

    new_cache = {}
    for row in rows:
        key = (row["level"], row["category"])
        new_cache[key] = {
            "criteria_labels": row["criteria_labels"],
            "pairwise_matrix": row["pairwise_matrix"],
            "priority_vector": row["priority_vector"],
            "lambda_max": row["lambda_max"],
            "ci": row["consistency_index"],
            "ri": row["random_index"],
            "cr": row["consistency_ratio"],
            "is_consistent": row["is_consistent"],
            "updated_by_admin_email": row["updated_by_admin_email"],
            "updated_at": row["updated_at"],
        }

    with _AHP_WEIGHTS_CACHE_LOCK:
        _AHP_WEIGHTS_CACHE.clear()
        _AHP_WEIGHTS_CACHE.update(new_cache)


def get_ahp_weights(level: str, category: str | None = None):
    """Returns the cached AHP config dict for (level, category), or None if not
    yet configured -- callers should fall back to static defaults in that case."""
    cache_key = (level, category or AHP_GLOBAL_CATEGORY_SENTINEL)
    with _AHP_WEIGHTS_CACHE_LOCK:
        return _AHP_WEIGHTS_CACHE.get(cache_key)
