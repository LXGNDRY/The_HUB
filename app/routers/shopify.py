"""Authorized, GraphQL-first tenant Shopify reads."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import Principal, require_tenant_access
from app.database import get_db
from app.services.tenant_shopify import tenant_shopify_client

router = APIRouter()


@router.get("/{tenant_id}/products")
async def list_products(
    tenant_id: uuid.UUID,
    first: int = Query(default=25, ge=1, le=100),
    after: str | None = None,
    principal: Principal = Depends(require_tenant_access),
    db: AsyncSession = Depends(get_db),
):
    client = await tenant_shopify_client(db, tenant_id)
    query = """
    query TenantProducts($first: Int!, $after: String) {
      products(first: $first, after: $after) {
        nodes { id title handle status updatedAt totalInventory }
        pageInfo { hasNextPage endCursor }
      }
    }
    """
    return await client.graphql(query, {"first": first, "after": after})


@router.get("/{tenant_id}/orders")
async def list_orders(
    tenant_id: uuid.UUID,
    first: int = Query(default=25, ge=1, le=100),
    after: str | None = None,
    principal: Principal = Depends(require_tenant_access),
    db: AsyncSession = Depends(get_db),
):
    client = await tenant_shopify_client(db, tenant_id)
    query = """
    query TenantOrders($first: Int!, $after: String) {
      orders(first: $first, after: $after, sortKey: CREATED_AT, reverse: true) {
        nodes {
          id name createdAt displayFinancialStatus displayFulfillmentStatus
          totalPriceSet { shopMoney { amount currencyCode } }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
    """
    return await client.graphql(query, {"first": first, "after": after})


@router.get("/{tenant_id}/overview")
async def store_overview(
    tenant_id: uuid.UUID,
    principal: Principal = Depends(require_tenant_access),
    db: AsyncSession = Depends(get_db),
):
    client = await tenant_shopify_client(db, tenant_id)
    query = """
    query TenantOverview {
      shop { name myshopifyDomain currencyCode plan { publicDisplayName } }
      productsCount { count }
      ordersCount { count }
    }
    """
    return await client.graphql(query)
