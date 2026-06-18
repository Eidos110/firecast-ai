"""
Authentication and Authorization Module
========================================
Provides API key authentication for FastAPI endpoints.
"""

from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader
from typing import Optional
from src.config import get_config

# Define API key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """
    Dependency to validate API key from request header.
    
    Raises:
        HTTPException: 401 if API key is missing or invalid, 500 if server not configured
    """
    cfg = get_config()
    expected_key = cfg.api.secret_key
    
    if expected_key is None:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: API_SECRET_KEY not set. Contact administrator."
        )
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header."
        )
    
    if api_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key."
        )
    
    return api_key
