"""Trend analysis routes: saved background-scan results for a user, plus a debug status view.

The scanning itself lives in services/trend_scan.py; what the page receives is
assembled in services/trend_recommendations.py.
"""
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from db.queries import fetch_user_profile_by_id_async
from db.schema import get_users_primary_key_column_async
from db.trend_queries import fetch_latest_runs_status, fetch_result_report, open_trend_cursor
from services.auth_service import get_missing_trend_preferences
from services.trend_recommendations import build_user_trends
from services.trend_scan import get_in_flight_business_types, is_run_fresh


router = APIRouter()


async def _load_user_with_preferences(request: Request, user_id: int):
    async with request.app.state.db_pool.acquire() as conn:
        user_pk_column = await get_users_primary_key_column_async(conn)
        user_profile = await fetch_user_profile_by_id_async(conn, user_pk_column, user_id)

    if not user_profile:
        raise HTTPException(status_code=404, detail="User not found")

    missing_fields = get_missing_trend_preferences(user_profile)
    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Please complete your trend preferences first.",
                "missing_fields": missing_fields,
            },
        )
    return user_profile


@router.get("/users/{user_id}/trends")
async def get_user_trends(request: Request, user_id: int):
    try:
        user_profile = await _load_user_with_preferences(request, user_id)
        return await run_in_threadpool(build_user_trends, user_profile, "page")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/trends/rescan")
async def rescan_user_trends(request: Request, user_id: int):
    try:
        user_profile = await _load_user_with_preferences(request, user_id)
        return await run_in_threadpool(build_user_trends, user_profile, "manual", True)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


def _read_result_report(result_id: int):
    with open_trend_cursor() as cursor:
        return fetch_result_report(cursor, result_id)


@router.get("/trends/results/{result_id}")
async def get_trend_result_report(result_id: int):
    """The full saved /analyze report of one scanned spot (opens in the Report view)."""
    try:
        report = await run_in_threadpool(_read_result_report, result_id)
        if not report:
            raise HTTPException(status_code=404, detail="Scan result not found")
        return {"status": "success", "report": report}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


def _read_scan_status():
    with open_trend_cursor() as cursor:
        runs = fetch_latest_runs_status(cursor)
    return [
        {
            **{key: value for key, value in run.items() if key not in ("started_at", "finished_at")},
            "started_at": run["started_at"].isoformat() if run.get("started_at") else None,
            "finished_at": run["finished_at"].isoformat() if run.get("finished_at") else None,
            "is_fresh": run["status"] == "done" and is_run_fresh(run),
        }
        for run in runs
    ]


@router.get("/trends/scan-status")
async def get_trend_scan_status():
    """Debug view: the newest run of every business type and what is queued now."""
    try:
        runs = await run_in_threadpool(_read_scan_status)
        return {
            "status": "success",
            "in_flight": get_in_flight_business_types(),
            "runs": runs,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
