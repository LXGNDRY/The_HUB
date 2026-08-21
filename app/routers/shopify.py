"""Tenant Shopify routes, fail-closed until the shared client is available."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


def _pending() -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Tenant Shopify integration is quarantined pending Secret Manager and tenant authorization.",
    )


@router.post("/connect/{tenant_id}", include_in_schema=False)
async def connect_shopify(tenant_id: str):
    _pending()


@router.get("/{tenant_id}/products")
async def list_products(tenant_id: str, limit: int = 50):
    _pending()


@router.get("/{tenant_id}/orders")
async def list_orders(tenant_id: str, limit: int = 50):
    _pending()


@router.get("/{tenant_id}/overview")
async def store_overview(tenant_id: str):
    _pending()
