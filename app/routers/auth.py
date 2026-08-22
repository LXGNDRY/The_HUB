"""Tenant-bound Shopify OAuth with verified callback and Secret Manager storage."""

import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.identity import Principal, require_tenant_access
from app.core.security import create_oauth_state, parse_oauth_state
from app.core.security import validate_shop_domain, verify_shopify_oauth_query
from app.database import get_db
from app.models.security import CredentialReference
from app.models.tenant import Tenant
from app.services.secret_store import SecretStore

router = APIRouter()
SCOPES = "read_products,write_products,read_orders,read_themes,write_themes,read_customers"


@router.get("/shopify")
async def shopify_oauth_url(
    tenant_id: uuid.UUID,
    shop: str = Query(...),
    principal: Principal = Depends(require_tenant_access),
):
    shop = validate_shop_domain(shop)
    required = (
        settings.SHOPIFY_CLIENT_ID,
        settings.OAUTH_STATE_SIGNING_KEY,
        settings.SHOPIFY_REDIRECT_URI,
    )
    if not all(required):
        raise HTTPException(status_code=503, detail="Shopify OAuth is not configured.")
    state_value = create_oauth_state(str(tenant_id), shop, settings.OAUTH_STATE_SIGNING_KEY)
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
async def shopify_callback(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.SAAS_ENABLED:
        raise HTTPException(status_code=503, detail="SaaS integration is disabled.")
    query = dict(request.query_params)
    if not verify_shopify_oauth_query(query, settings.SHOPIFY_CLIENT_SECRET):
        raise HTTPException(status_code=401, detail="Invalid Shopify OAuth signature.")
    state = parse_oauth_state(query.get("state", ""), settings.OAUTH_STATE_SIGNING_KEY)
    shop = validate_shop_domain(query.get("shop", ""))
    if shop != state.shop:
        raise HTTPException(status_code=403, detail="OAuth shop mismatch.")
    tenant_id = uuid.UUID(state.tenant_id)
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": settings.SHOPIFY_CLIENT_ID,
                "client_secret": settings.SHOPIFY_CLIENT_SECRET,
                "code": query.get("code", ""),
            },
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Shopify token exchange failed.")
    token = str(response.json().get("access_token", ""))
    if not token:
        raise HTTPException(status_code=502, detail="Shopify returned no access token.")
    secret_resource = await SecretStore().put(str(tenant_id), "shopify-admin", token)
    existing = (
        await db.execute(
            select(CredentialReference).where(
                CredentialReference.tenant_id == tenant_id,
                CredentialReference.provider == "shopify",
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.secret_resource = secret_resource
        existing.is_active = True
    else:
        db.add(
            CredentialReference(
                tenant_id=tenant_id,
                provider="shopify",
                secret_resource=secret_resource,
            )
        )
    tenant.shopify_store_domain = shop
    await db.commit()
    return {"status": "connected", "shop": shop}
