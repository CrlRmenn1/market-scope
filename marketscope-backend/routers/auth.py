"""User registration, login, logout and password reset routes."""
from fastapi import APIRouter, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from core.auth import bearer_token, internal_error
from core.config import RESET_CODE_DEV_MODE, RESET_CODE_TTL_MINUTES, registration_is_open
from core.rate_limit import check_rate_limit, client_ip
from models.requests import (
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
)
from services.sessions import delete_session
from services.trend_scan import queue_scans_for_user


router = APIRouter()

FIFTEEN_MINUTES = 15 * 60
ONE_HOUR = 60 * 60


@router.post("/register")
async def register(request: Request, user: RegisterUser):
    if not registration_is_open():
        raise HTTPException(status_code=403, detail="New sign-ups are closed right now.")
    check_rate_limit(f"register:ip:{client_ip(request)}", 10, ONE_HOUR, "Too many sign-ups from this network. Try again later.")
    try:
        return await auth_register_user(request.app.state.db_pool, user)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise internal_error(e, "register")


@router.post("/login")
async def login(request: Request, user: LoginUser):
    too_many = "Too many login attempts. Try again in 15 minutes."
    email = user.email.strip().lower()
    check_rate_limit(f"login:ip:{client_ip(request)}", 30, FIFTEEN_MINUTES, too_many)
    check_rate_limit(f"login:email-ip:{email}:{client_ip(request)}", 10, FIFTEEN_MINUTES, too_many)
    # Higher, because anyone can spend this one on someone else's email.
    check_rate_limit(f"login:email:{email}", 30, FIFTEEN_MINUTES, too_many)
    try:
        response = await auth_login_user(request.app.state.db_pool, user)
        if response.get("trend_preferences_completed"):
            # Start background trend scans now so results are ready by the time
            # the user opens Trends. Fresh saved results are reused, not rescanned.
            await run_in_threadpool(queue_scans_for_user, response["user"], "login")
        return response
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise internal_error(e, "login")


@router.post("/logout")
async def logout(request: Request, authorization: str | None = Header(default=None)):
    try:
        token = bearer_token(authorization)
        if token:
            await delete_session(request.app.state.db_pool, token)
        return {"status": "success"}
    except Exception as e:
        raise internal_error(e, "logout")


@router.post("/forgot-password")
async def forgot_password(request: Request, payload: ForgotPasswordRequest):
    too_many = "Too many code requests. Try again in 15 minutes."
    check_rate_limit(f"forgot:ip:{client_ip(request)}", 10, FIFTEEN_MINUTES, too_many)
    check_rate_limit(f"forgot:email:{payload.email.strip().lower()}", 3, FIFTEEN_MINUTES, too_many)
    try:
        response = await auth_forgot_password(request.app.state.db_pool, payload, RESET_CODE_TTL_MINUTES)
        if RESET_CODE_DEV_MODE and response.get("status") == "success" and payload.email:
            # dev-only hint is handled in the service flow; keep compatibility here if needed later
            pass
        return response
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise internal_error(e, "forgot password")


@router.post("/reset-password")
async def reset_password(request: Request, payload: ResetPasswordRequest):
    check_rate_limit(f"reset:ip:{client_ip(request)}", 20, FIFTEEN_MINUTES, "Too many attempts. Try again in 15 minutes.")
    try:
        return await auth_reset_password(request.app.state.db_pool, payload)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise internal_error(e, "reset password")
