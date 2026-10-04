"""User registration, login, and password reset routes."""
from fastapi import APIRouter, HTTPException, Request

from core.config import RESET_CODE_DEV_MODE, RESET_CODE_TTL_MINUTES
from models.requests import (
    DirectResetPasswordRequest,
    ForgotPasswordRequest,
    LoginUser,
    RegisterUser,
    ResetPasswordRequest,
)
from services.auth_service import (
    forgot_password as auth_forgot_password,
    login_user as auth_login_user,
    register_user as auth_register_user,
    reset_password as auth_reset_password,
    reset_password_direct as auth_reset_password_direct,
)
from services.trend_scan import trigger_trend_warmup_after_login


router = APIRouter()


@router.post("/register")
async def register(request: Request, user: RegisterUser):
    try:
        return await auth_register_user(request.app.state.db_pool, user)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login")
async def login(request: Request, user: LoginUser):
    try:
        response = await auth_login_user(request.app.state.db_pool, user)
        trigger_trend_warmup_after_login(radius=340)
        return response
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/forgot-password")
async def forgot_password(request: Request, payload: ForgotPasswordRequest):
    try:
        response = await auth_forgot_password(request.app.state.db_pool, payload, RESET_CODE_TTL_MINUTES)
        if RESET_CODE_DEV_MODE and response.get("status") == "success" and payload.email:
            # dev-only hint is handled in the service flow; keep compatibility here if needed later
            pass
        return response
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-password")
async def reset_password(request: Request, payload: ResetPasswordRequest):
    try:
        return await auth_reset_password(request.app.state.db_pool, payload)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-password-direct")
async def reset_password_direct(request: Request, payload: DirectResetPasswordRequest):
    try:
        return await auth_reset_password_direct(request.app.state.db_pool, payload)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))
