"""Admin token check shared by every /admin route."""
import hmac

from fastapi import HTTPException

from core.config import ADMIN_TOKEN


def verify_admin_token(x_admin_token: str | None):
    # ADMIN_TOKEN is None when production has no strong secret: nobody gets in.
    if not ADMIN_TOKEN or not x_admin_token or not hmac.compare_digest(x_admin_token.encode("utf-8"), ADMIN_TOKEN.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Unauthorized admin access")
