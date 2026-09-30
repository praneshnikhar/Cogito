"""Auth dependencies. Write/admin routes require the ADMIN_TOKEN (sent as
`Authorization: Bearer <token>` or `X-Admin-Token`). All other routes stay
open so read paths (search, ask) work key-free in demos."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from app.config import settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    token = x_admin_token or ""
    ok = token and hmac.compare_digest(token, settings.admin_token)
    if not ok:
        raise HTTPException(status_code=401, detail="missing or invalid admin token")