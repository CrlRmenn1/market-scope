"""Admin routes for AHP pairwise matrices (criteria and saturation weights)."""
import psycopg2
from fastapi import APIRouter, HTTPException, Header
from psycopg2.extras import Json, RealDictCursor

from constants.msme import MSME_CATEGORY_PROFILES
from core.config import ADMIN_EMAIL
from core.database import DB_CONFIG
from core.security import verify_admin_token
from db.schema import AHP_GLOBAL_CATEGORY_SENTINEL
from models.requests import AhpPairwiseSubmitRequest
from services.ahp import AHPValidationError, build_reciprocal_matrix, solve_ahp
from services.ahp_weights import _load_ahp_weights_cache


router = APIRouter()


AHP_LEVEL_EXPECTED_SIZE = {"criteria": 3, "saturation": 4}


def _ahp_judgments_to_upper_triangle(judgments: dict) -> dict:
    """Converts {"i,j": value} string-keyed JSON judgments into {(i, j): value}
    tuple-keyed judgments expected by ahp.build_reciprocal_matrix."""
    upper_triangle = {}
    for key, value in (judgments or {}).items():
        try:
            i_str, j_str = str(key).split(",")
            i, j = int(i_str), int(j_str)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail=f"Malformed judgment key: {key!r}, expected 'i,j'")
        if i >= j:
            raise HTTPException(status_code=400, detail=f"Judgment key {key!r} must satisfy i < j (upper triangle only)")
        upper_triangle[(i, j)] = value
    return upper_triangle


def _ahp_config_row_to_dict(row: dict) -> dict:
    return {
        "level": row["level"],
        "category": row["category"],
        "criteria_labels": row["criteria_labels"],
        "pairwise_matrix": row["pairwise_matrix"],
        "priority_vector": row["priority_vector"],
        "lambda_max": row["lambda_max"],
        "consistency_index": row["consistency_index"],
        "random_index": row["random_index"],
        "consistency_ratio": row["consistency_ratio"],
        "is_consistent": row["is_consistent"],
        "updated_by_admin_email": row["updated_by_admin_email"],
        "updated_at": row["updated_at"],
    }


@router.post("/admin/ahp/matrix")
def admin_submit_ahp_matrix(payload: AhpPairwiseSubmitRequest, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        level = str(payload.level or "").strip().lower()
        if level not in AHP_LEVEL_EXPECTED_SIZE:
            raise HTTPException(status_code=400, detail="level must be either 'criteria' or 'saturation'")

        if level == "criteria":
            category = AHP_GLOBAL_CATEGORY_SENTINEL
        else:
            category = str(payload.category or "").strip().lower()
            if category not in MSME_CATEGORY_PROFILES:
                raise HTTPException(status_code=400, detail=f"Unknown business category: {payload.category!r}")

        expected_n = AHP_LEVEL_EXPECTED_SIZE[level]
        if len(payload.criteria_labels) != expected_n:
            raise HTTPException(
                status_code=400,
                detail=f"criteria_labels must have exactly {expected_n} entries for level={level!r}"
            )

        upper_triangle = _ahp_judgments_to_upper_triangle(payload.judgments)
        matrix = build_reciprocal_matrix(upper_triangle, expected_n)
        solved = solve_ahp(matrix)

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            INSERT INTO ahp_weight_configs (
                level, category, criteria_labels, pairwise_matrix, priority_vector,
                lambda_max, consistency_index, random_index, consistency_ratio,
                is_consistent, updated_by_admin_email
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (level, category) DO UPDATE SET
                criteria_labels = EXCLUDED.criteria_labels,
                pairwise_matrix = EXCLUDED.pairwise_matrix,
                priority_vector = EXCLUDED.priority_vector,
                lambda_max = EXCLUDED.lambda_max,
                consistency_index = EXCLUDED.consistency_index,
                random_index = EXCLUDED.random_index,
                consistency_ratio = EXCLUDED.consistency_ratio,
                is_consistent = EXCLUDED.is_consistent,
                updated_by_admin_email = EXCLUDED.updated_by_admin_email,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            (
                level,
                category,
                Json(payload.criteria_labels),
                Json(matrix),
                Json(solved["priority_vector"]),
                solved["lambda_max"],
                solved["ci"],
                solved["ri"],
                solved["cr"],
                solved["is_consistent"],
                ADMIN_EMAIL,
            )
        )
        saved = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        _load_ahp_weights_cache()

        return {"status": "success", "config": _ahp_config_row_to_dict(saved)}
    except AHPValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/ahp/matrix")
def admin_get_ahp_matrix(level: str, category: str | None = None, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        level = str(level or "").strip().lower()
        if level not in AHP_LEVEL_EXPECTED_SIZE:
            raise HTTPException(status_code=400, detail="level must be either 'criteria' or 'saturation'")
        lookup_category = AHP_GLOBAL_CATEGORY_SENTINEL if level == "criteria" else str(category or "").strip().lower()

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT * FROM ahp_weight_configs WHERE level = %s AND category = %s",
            (level, lookup_category)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="No AHP matrix configured for this level/category yet")

        return {"status": "success", "config": _ahp_config_row_to_dict(row)}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/ahp/matrices")
def admin_list_ahp_matrices(x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM ahp_weight_configs ORDER BY level, category")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        configured_by_key = {(row["level"], row["category"]): row for row in rows}
        entries = []

        criteria_row = configured_by_key.get(("criteria", AHP_GLOBAL_CATEGORY_SENTINEL))
        entries.append({
            "level": "criteria",
            "category": AHP_GLOBAL_CATEGORY_SENTINEL,
            "is_configured": criteria_row is not None,
            "is_consistent": criteria_row["is_consistent"] if criteria_row else None,
            "consistency_ratio": criteria_row["consistency_ratio"] if criteria_row else None,
            "updated_by_admin_email": criteria_row["updated_by_admin_email"] if criteria_row else None,
            "updated_at": criteria_row["updated_at"] if criteria_row else None,
        })

        for category_key in MSME_CATEGORY_PROFILES:
            row = configured_by_key.get(("saturation", category_key))
            entries.append({
                "level": "saturation",
                "category": category_key,
                "is_configured": row is not None,
                "is_consistent": row["is_consistent"] if row else None,
                "consistency_ratio": row["consistency_ratio"] if row else None,
                "updated_by_admin_email": row["updated_by_admin_email"] if row else None,
                "updated_at": row["updated_at"] if row else None,
            })

        return {"status": "success", "configs": entries}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/ahp/matrix")
def admin_delete_ahp_matrix(level: str, category: str | None = None, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        level = str(level or "").strip().lower()
        if level not in AHP_LEVEL_EXPECTED_SIZE:
            raise HTTPException(status_code=400, detail="level must be either 'criteria' or 'saturation'")
        lookup_category = AHP_GLOBAL_CATEGORY_SENTINEL if level == "criteria" else str(category or "").strip().lower()

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "DELETE FROM ahp_weight_configs WHERE level = %s AND category = %s RETURNING id",
            (level, lookup_category)
        )
        deleted = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not deleted:
            raise HTTPException(status_code=404, detail="No AHP matrix configured for this level/category")

        _load_ahp_weights_cache()
        return {"status": "success", "reverted_to": "static_fallback"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
