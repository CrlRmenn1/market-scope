"""Who is calling? FastAPI dependencies for routes that need a logged-in user."""
from fastapi import Depends, Header, HTTPException, Request

from core.rate_limit import client_ip
from services.sessions import find_session_user_id


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _log_denied(request: Request, status: int, reason: str) -> None:
    print(f"[auth] denied {status} {reason}: {request.method} {request.url.path} from {client_ip(request)}", flush=True)


async def require_user(request: Request, authorization: str | None = Header(default=None)) -> int:
    """The logged-in user's id, or 401."""
    token = bearer_token(authorization)
    user_id = await find_session_user_id(request.app.state.db_pool, token) if token else None
    if user_id is None:
        _log_denied(request, 401, "no valid session")
        raise HTTPException(status_code=401, detail="Please log in again.")
    return user_id


async def require_same_user(request: Request, user_id: int, current_user_id: int = Depends(require_user)) -> int:
    """For /users/{user_id}/... routes: only that user may use them."""
    if current_user_id != user_id:
        _log_denied(request, 403, f"user {current_user_id} tried user {user_id}")
        raise HTTPException(status_code=403, detail="You can only access your own account.")
    return user_id


def internal_error(error: Exception, where: str) -> HTTPException:
    """Logs the real error and returns a generic one, so database details stay private."""
    print(f"[error] {where}: {error!r}", flush=True)
    return HTTPException(status_code=500, detail="Something went wrong on our side. Try again in a moment.")
