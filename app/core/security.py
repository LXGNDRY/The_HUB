"""Security primitives shared by the hub-backend HTTP surface."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


SHOP_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$", re.IGNORECASE)


def constant_time_equal(left: str, right: str) -> bool:
    """Compare secrets without leaking useful timing information."""
    return bool(left and right) and hmac.compare_digest(left.encode(), right.encode())


def validate_shop_domain(shop: str) -> str:
    """Return a normalized Shopify hostname or reject it."""
    normalized = shop.strip().lower()
    if not SHOP_DOMAIN_RE.fullmatch(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Shopify shop domain.")
    return normalized


def verify_shopify_webhook(raw_body: bytes, provided_hmac: str, client_secret: str) -> bool:
    digest = hmac.new(client_secret.encode(), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return constant_time_equal(expected, provided_hmac)


def verify_shopify_oauth_query(query: dict[str, str], client_secret: str) -> bool:
    """Verify the HMAC attached to a Shopify OAuth callback."""
    provided = query.get("hmac", "")
    message = "&".join(f"{key}={value}" for key, value in sorted(query.items()) if key != "hmac")
    expected = hmac.new(client_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return constant_time_equal(expected, provided)


@dataclass(frozen=True)
class OAuthState:
    nonce: str
    tenant_id: str
    shop: str
    issued_at: int


def create_oauth_state(tenant_id: str, shop: str, signing_key: str) -> str:
    """Create a short-lived signed state value without storing process-local state."""
    payload = f"{secrets.token_urlsafe(24)}|{tenant_id}|{validate_shop_domain(shop)}|{int(time.time())}"
    signature = hmac.new(signing_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{signature}".encode()).decode()


def parse_oauth_state(value: str, signing_key: str, max_age_seconds: int = 600) -> OAuthState:
    try:
        decoded = base64.urlsafe_b64decode(value.encode()).decode()
        nonce, tenant_id, shop, issued_at_raw, signature = decoded.split("|", 4)
        payload = f"{nonce}|{tenant_id}|{shop}|{issued_at_raw}"
        expected = hmac.new(signing_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        issued_at = int(issued_at_raw)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid OAuth state.")
    if not constant_time_equal(expected, signature) or time.time() - issued_at > max_age_seconds:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Expired or invalid OAuth state.")
    return OAuthState(nonce=nonce, tenant_id=tenant_id, shop=validate_shop_domain(shop), issued_at=issued_at)


async def require_admin_api_key(request: Request, configured_key: str) -> None:
    supplied = request.headers.get("X-Hub-Admin-Key", "")
    if not configured_key or not constant_time_equal(supplied, configured_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
