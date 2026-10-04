"""User profile and analysis history routes. Trend routes live in routers/trends.py."""
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from models.requests import UpdateUserProfile
from services.auth_service import get_missing_trend_preferences
from services.trend_scan import queue_scans_for_user
from services.user_service import (
    delete_user_history_item as user_delete_history_item,
    get_user_history as user_get_history,
    get_user_history_item as user_get_history_item,
    get_user_profile as user_get_profile,
    mark_user_onboarding_seen as user_mark_onboarding_seen,
    update_user_profile as user_update_profile,
)


router = APIRouter()


@router.get("/users/{user_id}")
async def get_user_profile(request: Request, user_id: int):
    try:
        profile = await user_get_profile(request.app.state.db_pool, user_id)

        if not profile:
            raise HTTPException(status_code=404, detail="User not found")

        return {"status": "success", "user": dict(profile)}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}")
async def update_user_profile(request: Request, user_id: int, payload: UpdateUserProfile):
    try:
        updated_user = await user_update_profile(request.app.state.db_pool, user_id, payload)
        if updated_user and not get_missing_trend_preferences(dict(updated_user)):
            # Preferences may have changed: scan any newly picked business types.
            await run_in_threadpool(queue_scans_for_user, dict(updated_user), "profile")
        return {"status": "success", "user": dict(updated_user) if updated_user else None}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/onboarding-seen")
async def mark_onboarding_seen(request: Request, user_id: int):
    try:
        updated = await user_mark_onboarding_seen(request.app.state.db_pool, user_id)
        return {"status": "success", "onboarding_seen": bool(updated["onboarding_seen"])}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/history")
async def get_user_history(request: Request, user_id: int):
    try:
        history = await user_get_history(request.app.state.db_pool, user_id)
        return {"status": "success", "history": history}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/history/{history_id}")
async def get_user_history_item(request: Request, user_id: int, history_id: int):
    try:
        history_item = await user_get_history_item(request.app.state.db_pool, user_id, history_id)

        if not history_item:
            raise HTTPException(status_code=404, detail="History item not found")

        return {"status": "success", "history": history_item}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}/history/{history_id}")
async def delete_user_history_item(request: Request, user_id: int, history_id: int):
    try:
        deleted_row = await user_delete_history_item(request.app.state.db_pool, user_id, history_id)

        if not deleted_row:
            return {"status": "success", "deleted_history_id": history_id, "already_missing": True}

        return {"status": "success", "deleted_history_id": deleted_row[0]}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))
