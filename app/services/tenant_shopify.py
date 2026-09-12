"""Build tenant-bound Shopify clients from Secret Manager references."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.shopify.client import ShopifyClient
from app.models.security import CredentialReference
from app.models.tenant import Tenant
from app.services.secret_store import SecretStore


async def tenant_shopify_client(db: AsyncSession, tenant_id: uuid.UUID) -> ShopifyClient:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    credential = (
        await db.execute(
            select(CredentialReference).where(
                CredentialReference.tenant_id == tenant_id,
                CredentialReference.provider == "shopify",
                CredentialReference.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if credential is None or not tenant.shopify_store_domain:
        raise HTTPException(status_code=409, detail="Shopify is not connected for this tenant.")
    store = SecretStore()

    async def token_provider() -> str:
        return await store.access(credential.secret_resource)

    return ShopifyClient(tenant.shopify_store_domain, token_provider)
