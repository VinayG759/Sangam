import hmac
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

_DEV_FALLBACK_PEPPER = "dev-fallback-pepper-1234567890abcdef"
_warned_fallback = False


def hash_channel_user(channel_user_id: str) -> str:
    """
    Hash a user ID (e.g. Telegram chat ID or WhatsApp number) securely.
    Uses HMAC-SHA256 with a pepper to ensure the raw identity cannot be derived.
    """
    global _warned_fallback
    pepper = os.getenv("REPORTER_HASH_PEPPER", _DEV_FALLBACK_PEPPER)
    if pepper == _DEV_FALLBACK_PEPPER and not _warned_fallback:
        # This value is public in source control. Falling back to it silently
        # would mean anyone who reads the repo can reverse every reporter_hash
        # in a deployment that forgot to set REPORTER_HASH_PEPPER -- the exact
        # anonymity guarantee this hash exists to provide. Warn loudly instead.
        logger.warning(
            "REPORTER_HASH_PEPPER is not set -- using a hardcoded dev fallback "
            "pepper that is public in source control. Reporter identity hashes "
            "are NOT anonymous. Set REPORTER_HASH_PEPPER before deploying."
        )
        _warned_fallback = True

    # Use HMAC to generate a deterministic, non-reversible hash
    h = hmac.new(
        pepper.encode('utf-8'),
        channel_user_id.encode('utf-8'),
        hashlib.sha256
    )
    return h.hexdigest()
