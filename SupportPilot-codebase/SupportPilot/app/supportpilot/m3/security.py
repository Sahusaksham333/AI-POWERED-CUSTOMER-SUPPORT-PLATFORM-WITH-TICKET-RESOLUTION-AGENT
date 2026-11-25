"""Administrator access guard for M3 operational endpoints."""
from __future__ import annotations
import hmac
import os
from fastapi import Header, HTTPException


def require_m3_admin(
    x_supportpilot_admin_key: str | None = Header(default=None),
) -> dict[str, bool]:
    expected = os.getenv("SUPPORTPILOT_ADMIN_API_KEY", "").strip()
    if len(expected) < 32:
        raise HTTPException(
            status_code=503,
            detail=(
                "Milestone 3 is locked. Configure SUPPORTPILOT_ADMIN_API_KEY "
                "with a randomly generated secret of at least 32 characters in .env."
            ),
        )
    if not x_supportpilot_admin_key or not hmac.compare_digest(x_supportpilot_admin_key, expected):
        raise HTTPException(status_code=401, detail="Administrator key missing or invalid for Milestone 3.")
    return {"authorized": True}
