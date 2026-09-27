"""Admin auth, reporter-ID hashing, and constant-time secret checks."""

import hashlib
import hmac

from fastapi import Header, HTTPException

from app.core.config import get_settings


def secrets_match(provided: str | None, expected: str) -> bool:
    """False whenever the expected secret is unset — every check fails closed."""
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())


def require_admin(authorization: str | None = Header(default=None)) -> None:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets_match(token, get_settings().ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Admin token required")


def reporter_hash(channel: str, sender_id: str) -> str:
    """HMAC-SHA256 of the channel's user ID. The raw ID is never stored anywhere."""
    pepper = get_settings().REPORTER_HASH_PEPPER.encode()
    return hmac.new(pepper, f"{channel}:{sender_id}".encode(), hashlib.sha256).hexdigest()
