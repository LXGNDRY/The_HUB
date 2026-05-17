"""
API Key authentication middleware.
All protected routes require: X-API-Key: <DASHBOARD_API_KEY>
Set DASHBOARD_API_KEY in your .env file.
"""

import os
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)
_EXPECTED_KEY = os.getenv("DASHBOARD_API_KEY", "")


def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """
    Validates the X-API-Key header against DASHBOARD_API_KEY env var.
    Raises 403 on mismatch. Raises 500 if key is not configured.
    """
    if not _EXPECTED_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DASHBOARD_API_KEY is not configured on the server.",
        )
    if api_key != _EXPECTED_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )
    return api_key
