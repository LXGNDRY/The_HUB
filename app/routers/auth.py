"""
Auth router — OAuth flow for Shopify store connections.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.tenant import Tenant

router = APIRouter()


@router.get("/shopify")
async def shopify_oauth_url(tenant_id: str = Query(...)):
    """Generate Shopify OAuth URL for a tenant."""
    from app.core.config import settings
    scopes = "read_products,write_products,read_orders,read_themes,write_themes,read_customers,write_customers,read_shipping,write_shipping,read_markets"
    url = (
        f"https://{settings.SHOPIFY_REDIRECT_URI.split('/')[2]}/admin/oauth/authorize"
        f"?client_id={settings.SHOPIFY_CLIENT_ID}"
        f"&scope={scopes}"
        f"&redirect_uri={settings.SHOPIFY_REDIRECT_URI}"
        f"&state={tenant_id}"
    )
    return {"oauth_url": url}


@router.get("/shopify/callback")
async def shopify_callback(
    code: str = Query(...),
    state: str = Query(...),
    shop: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle Shopify OAuth callback."""
    # TODO: Exchange code for access token, update tenant
    return {"shop": shop, "tenant_id": state, "status": "connected"}