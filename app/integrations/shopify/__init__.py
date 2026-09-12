"""Tenant-aware Shopify integration package."""

from app.integrations.shopify.client import ShopifyClient, ShopifyError

__all__ = ["ShopifyClient", "ShopifyError"]
