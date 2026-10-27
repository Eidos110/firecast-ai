"""
Authentication and Authorization Module
=======================================
Provides API key authentication for FastAPI endpoints.
"""

import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from src.config import get_config

# Known placeholder values that must never be accepted as real API keys.
# Prevents accidental deployment with a non-secret literal (e.g. in .env).
_PLACEHOLDER_API_KEYS = frozenset(
    {
        "",
        "your_secure_api_secret_key_here",
        "changeme",
        "change_me",
        "change_me_to_a_random_secret_at_least_32_chars",
        "CHANGE_THIS_TO_A_STRONG_RANDOM_SECRET_MIN_64_CHARS",
        "CHANGE_ME_TO_A_RANDOM_SECRET_AT_LEAST_32_CHARS",
    }
)

# Define API key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """
    Dependency to validate API key from request header.

    Raises:
        HTTPException: 500 if server misconfigured (missing/placeholder secret),
                       401 if API key missing or invalid.
    """
    cfg = get_config()
    expected_key = cfg.api.secret_key

    if not expected_key or expected_key in _PLACEHOLDER_API_KEYS:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: API_SECRET_KEY not set or is a known placeholder. "
            "Set a strong random secret (>=32 chars) via env/secret manager.",
        )

    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key. Include X-API-Key header.")

    if not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid API key.")

    return api_key
