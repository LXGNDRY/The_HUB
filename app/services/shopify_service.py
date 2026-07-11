"""
Shopify service — proxies requests to the existing shopify module.
This wraps the existing modules/shopify.py into the FastAPI service layer.
"""

import sys
import os
from typing import Optional

# Allow importing from the project root (existing modules)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings


class ShopifyService:
    """Service layer wrapping the existing Shopify module."""

    def __init__(self, store_domain: str = "", access_token: str = ""):
        self.store_domain = store_domain
        self.access_token = access_token

    def _configure_module(self):
        """Set environment variables for the shopify module, then import it."""
        if self.store_domain:
            os.environ["SHOPIFY_STORE_DOMAIN"] = self.store_domain
        if self.access_token:
            os.environ["SHOPIFY_ADMIN_TOKEN"] = self.access_token
        # Import the existing module
        import modules.shopify as shopify_mod
        return shopify_mod

    def test_connection(self) -> dict:
        """Test the Shopify connection."""
        shopify = self._configure_module()
        return shopify.test_connection()

    def get_overview(self) -> dict:
        """Get store overview."""
        shopify = self._configure_module()
        return shopify.store_overview()

    def list_products(self, limit: int = 50, status: str = "any") -> dict:
        shopify = self._configure_module()
        return shopify.list_products(limit=limit, status=status)

    def list_orders(self, limit: int = 50, status: str = "any") -> dict:
        shopify = self._configure_module()
        return shopify.list_orders(limit=limit, status=status)

    def list_themes(self) -> dict:
        shopify = self._configure_module()
        return shopify.list_themes()

    def list_customers(self, limit: int = 50) -> dict:
        shopify = self._configure_module()
        return shopify.list_customers(limit=limit)

    def list_webhooks(self) -> dict:
        shopify = self._configure_module()
        return shopify.list_webhooks()

    def list_markets(self) -> dict:
        shopify = self._configure_module()
        return shopify.list_markets()

    def audit_shipping(self) -> dict:
        shopify = self._configure_module()
        return shopify.audit_shipping_profiles()