"""Admin token check shared by every /admin route."""
from fastapi import HTTPException

from core.config import ADMIN_TOKEN


def verify_admin_token(x_admin_token: str | None):
    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized admin access")
