"""Shopify OAuth initiation; callback persistence remains closed by design."""

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, status

from app.core.config import settings
from app.core.security import create_oauth_state, validate_shop_domain

router = APIRouter()

SCOPES = "read_products,write_products,read_orders,read_themes,write_themes,read_customers"


@router.get("/shopify")
async def shopify_oauth_url(tenant_id: str = Query(...), shop: str = Query(...)):
    shop = validate_shop_domain(shop)
    if not settings.SHOPIFY_CLIENT_ID or not settings.OAUTH_STATE_SIGNING_KEY or not settings.SHOPIFY_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Shopify OAuth is not configured.")
    state_value = create_oauth_state(tenant_id, shop, settings.OAUTH_STATE_SIGNING_KEY)
    query = urlencode(
        {
            "client_id": settings.SHOPIFY_CLIENT_ID,
            "scope": SCOPES,
            "redirect_uri": settings.SHOPIFY_REDIRECT_URI,
            "state": state_value,
        }
    )
    return {"oauth_url": f"https://{shop}/admin/oauth/authorize?{query}"}


@router.get("/shopify/callback", include_in_schema=False)
async def shopify_callback():
    # Token persistence stays fail-closed until tenant-bound Secret Manager storage lands.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="OAuth callback is quarantined pending secure tenant credential storage.",
    )
