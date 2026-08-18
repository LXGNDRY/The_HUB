"""
Shopify OAuth 2.0 install + callback flow.

GET /auth/shopify?shop=mystore.myshopify.com  → redirects to Shopify consent screen
GET /auth/shopify/callback?code=…&shop=…      → exchanges code, returns token

Mount in api/main.py WITHOUT the X-API-Key guard:
  app.include_router(oauth.router, tags=["OAuth"])
"""

import os
import secrets
import httpx
from fastapi import APIRouter, Response
from fastapi.responses import RedirectResponse

router = APIRouter()

SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
APP_URL = os.getenv("APP_URL", "")

# In-memory CSRF state store — sufficient for single-tenant; swap for Redis in multi-tenant
_state_store: dict[str, str] = {}

SCOPES = (
    "read_products,write_products,"
    "read_orders,"
    "read_content,write_content,"
    "read_inventory,write_inventory,"
    "read_analytics,"
    "read_draft_orders,write_draft_orders,"
    "read_fulfillments,write_fulfillments,"
    "read_price_rules,write_price_rules,"
    "read_themes,write_themes,"
    "read_checkouts,"
    "read_customers,"
    "write_webhooks,read_webhooks"
)


@router.get("/auth/shopify", summary="Begin Shopify OAuth install")
def shopify_install(shop: str):
    """Redirect merchant to Shopify consent screen."""
    state = secrets.token_urlsafe(16)
    _state_store[state] = shop
    redirect_uri = f"{APP_URL}/auth/shopify/callback"
    url = (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={SHOPIFY_CLIENT_ID}"
        f"&scope={SCOPES}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )
    return RedirectResponse(url)


@router.get("/auth/shopify/callback", summary="Shopify OAuth callback — exchange code for token")
async def shopify_callback(shop: str, code: str, state: str):
    """
    Exchange the temporary code for a permanent access token.
    For a single-store custom app this token can be stored in Secret Manager.
    Returns the token as JSON for manual storage on first install.
    """
    if _state_store.pop(state, None) != shop:
        return Response("Invalid or expired state parameter.", status_code=403)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": SHOPIFY_CLIENT_ID,
                "client_secret": SHOPIFY_CLIENT_SECRET,
                "code": code,
            },
            timeout=15,
        )

    if not resp.is_success:
        return Response(f"Token exchange failed: {resp.text}", status_code=502)

    token_data = resp.json()
    access_token = token_data.get("access_token", "")

    return {
        "shop": shop,
        "access_token": access_token,
        "scope": token_data.get("scope", ""),
        "status": "installed",
        "note": "Store this access_token as SHOPIFY_ADMIN_TOKEN in your Cloud Run env / Secret Manager.",
    }
