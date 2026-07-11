"""
Shopify integration router — proxy calls to the Shopify module.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.tenant import Tenant

router = APIRouter()


class ShopifyConnect(BaseModel):
    store_domain: str
    access_token: str


@router.post("/connect/{tenant_id}")
async def connect_shopify(
    tenant_id: str, data: ShopifyConnect, db: AsyncSession = Depends(get_db)
):
    """Connect a Shopify store to a tenant."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Tenant not found.")

    tenant.shopify_store_domain = data.store_domain
    tenant.shopify_access_token = data.access_token
    await db.commit()
    return {"status": "connected", "store": data.store_domain}


@router.get("/{tenant_id}/products")
async def list_products(tenant_id: str, limit: int = 50):
    """List products for a tenant's Shopify store."""
    # TODO: Load tenant, use shopify module to proxy
    return {"tenant_id": tenant_id, "endpoint": "products", "note": "Shopify module integration pending"}


@router.get("/{tenant_id}/orders")
async def list_orders(tenant_id: str, limit: int = 50):
    """List orders for a tenant's Shopify store."""
    return {"tenant_id": tenant_id, "endpoint": "orders", "note": "Shopify module integration pending"}


@router.get("/{tenant_id}/overview")
async def store_overview(tenant_id: str):
    """Store health snapshot."""
    return {"tenant_id": tenant_id, "endpoint": "overview", "note": "Shopify module integration pending"}