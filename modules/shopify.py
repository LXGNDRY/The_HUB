"""
Shopify Admin API module for GCP Bot.
Covers: Products, Orders, Customers, Inventory, Content (Pages/Blogs/Articles),
        Themes, Price Rules / Discounts, SEO meta patching.

All calls use the Admin REST API v2026-04.
Token is obtained (and auto-refreshed) via OAuth Client Credentials Grant
using SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET env vars.

Refresh strategy:
  - Token is cached in module memory with its expiry timestamp.
  - Before every API call, _ensure_token() checks if we are within
    REFRESH_BUFFER_SECONDS (300s = 5 min) of expiry.
  - If so, a new grant is issued and the cache is updated.
  - Bootstrap: if SHOPIFY_ADMIN_TOKEN is pre-set in env, it is used
    as the initial token with an assumed expiry of 23h from boot,
    so the first refresh happens ~1 hour before it would actually expire.

Store domain is SHOPIFY_STORE_DOMAIN (default: lngndny.myshopify.com).
"""

import os
import time
import threading
import logging
import requests
from typing import Optional

logger = logging.getLogger("gcp-bot.shopify")

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
SHOPIFY_STORE_DOMAIN: str = os.getenv("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
SHOPIFY_CLIENT_ID: str = os.getenv("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET: str = os.getenv("SHOPIFY_CLIENT_SECRET", "")
API_VERSION = "2026-04"
BASE_URL = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{API_VERSION}"
OAUTH_URL = f"https://{SHOPIFY_STORE_DOMAIN}/admin/oauth/access_token"

# How many seconds before expiry to proactively refresh
REFRESH_BUFFER_SECONDS = 300  # 5 minutes


# ─────────────────────────────────────────────
# Token cache (module-level singleton)
# ─────────────────────────────────────────────
class _TokenCache:
    """
    Thread-safe in-memory token cache.
    Stores the current access token and its Unix expiry timestamp.
    """
    def __init__(self):
        self._lock = threading.Lock()
        # Seed from env var if provided (assumed ~23h remaining at boot)
        _env_token = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
        if _env_token:
            self._token: str = _env_token
            # Assume token was just issued — set expiry to 23h from now
            # so we refresh ~1h before the real 24h window closes
            self._expires_at: float = time.time() + (23 * 3600)
            logger.info("Shopify token seeded from SHOPIFY_ADMIN_TOKEN env var (assumed 23h TTL).")
        else:
            self._token = ""
            self._expires_at = 0.0

    def get(self) -> str:
        """Return the current token, refreshing first if near expiry."""
        with self._lock:
            if time.time() >= (self._expires_at - REFRESH_BUFFER_SECONDS):
                self._refresh()
            return self._token

    def _refresh(self):
        """Fetch a new token via Client Credentials Grant (called under lock)."""
        if not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
            raise RuntimeError(
                "SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET must be set to refresh the admin token."
            )
        logger.info("Shopify token near expiry — requesting new Client Credentials token...")
        r = requests.post(
            OAUTH_URL,
            json={
                "client_id": SHOPIFY_CLIENT_ID,
                "client_secret": SHOPIFY_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", 86399))
        self._expires_at = time.time() + expires_in
        logger.info(
            "Shopify token refreshed. New token expires in %ds (%s).",
            expires_in,
            time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(self._expires_at)),
        )

    def status(self) -> dict:
        """Return cache status for diagnostics."""
        with self._lock:
            ttl = max(0, int(self._expires_at - time.time()))
            return {
                "token_set": bool(self._token),
                "token_prefix": self._token[:12] + "..." if self._token else None,
                "expires_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._expires_at)),
                "ttl_seconds": ttl,
                "ttl_minutes": round(ttl / 60, 1),
                "will_refresh_in_seconds": max(0, int(self._expires_at - REFRESH_BUFFER_SECONDS - time.time())),
            }


# Module-level singleton
_token_cache = _TokenCache()


def _headers() -> dict:
    return {
        "X-Shopify-Access-Token": _token_cache.get(),
        "Content-Type": "application/json",
    }


def _get(path: str, params: Optional[dict] = None) -> dict:
    url = f"{BASE_URL}{path}"
    r = requests.get(url, headers=_headers(), params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}{path}"
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def _put(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}{path}"
    r = requests.put(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def _delete(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    r = requests.delete(url, headers=_headers(), timeout=30)
    r.raise_for_status()
    return {"deleted": True, "status_code": r.status_code}


# ─────────────────────────────────────────────
# Health / Connection Test
# ─────────────────────────────────────────────

def token_status() -> dict:
    """Return current token cache status without making an API call."""
    return _token_cache.status()


def force_token_refresh() -> dict:
    """Force an immediate token refresh regardless of TTL."""
    with _token_cache._lock:
        _token_cache._expires_at = 0.0  # force expiry
    _token_cache.get()  # triggers refresh
    return {"refreshed": True, **_token_cache.status()}


def test_connection() -> dict:
    """Ping the shop endpoint to verify admin token works."""
    data = _get("/shop.json")
    shop = data.get("shop", {})
    return {
        "connected": True,
        "shop_name": shop.get("name"),
        "shop_domain": shop.get("domain"),
        "myshopify_domain": shop.get("myshopify_domain"),
        "plan": shop.get("plan_name"),
        "currency": shop.get("currency"),
        "timezone": shop.get("iana_timezone"),
        "token_status": _token_cache.status(),
    }


# ─────────────────────────────────────────────
# Products
# ─────────────────────────────────────────────

def list_products(limit: int = 50, status: str = "any") -> dict:
    """List products with optional status filter (active/draft/archived/any)."""
    data = _get("/products.json", {"limit": limit, "status": status})
    products = data.get("products", [])
    return {
        "count": len(products),
        "products": [
            {
                "id": p["id"],
                "title": p["title"],
                "status": p["status"],
                "vendor": p.get("vendor"),
                "product_type": p.get("product_type"),
                "variants_count": len(p.get("variants", [])),
                "tags": p.get("tags", ""),
                "created_at": p.get("created_at"),
                "updated_at": p.get("updated_at"),
            }
            for p in products
        ],
    }


def get_product(product_id: int) -> dict:
    """Get full product detail by ID."""
    return _get(f"/products/{product_id}.json")


def create_product(title: str, body_html: str = "", vendor: str = "",
                   product_type: str = "", tags: str = "",
                   status: str = "draft") -> dict:
    """Create a new product (draft by default)."""
    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "tags": tags,
            "status": status,
        }
    }
    return _post("/products.json", payload)


def update_product(product_id: int, updates: dict) -> dict:
    """Update any product fields. Pass dict of fields to change."""
    payload = {"product": {"id": product_id, **updates}}
    return _put(f"/products/{product_id}.json", payload)


def update_product_seo(product_id: int, seo_title: str, seo_description: str) -> dict:
    """Patch SEO meta title and description for a product."""
    payload = {
        "product": {
            "id": product_id,
            "metafields_global_title_tag": seo_title,
            "metafields_global_description_tag": seo_description,
        }
    }
    return _put(f"/products/{product_id}.json", payload)


def product_count(status: str = "any") -> dict:
    """Get total product count."""
    return _get("/products/count.json", {"status": status})


# ─────────────────────────────────────────────
# Orders
# ─────────────────────────────────────────────

def list_orders(limit: int = 50, status: str = "any",
                financial_status: str = "any") -> dict:
    """List orders with optional status and financial_status filters."""
    params = {
        "limit": limit,
        "status": status,
        "financial_status": financial_status,
    }
    data = _get("/orders.json", params)
    orders = data.get("orders", [])
    return {
        "count": len(orders),
        "orders": [
            {
                "id": o["id"],
                "order_number": o.get("order_number"),
                "email": o.get("email"),
                "total_price": o.get("total_price"),
                "currency": o.get("currency"),
                "financial_status": o.get("financial_status"),
                "fulfillment_status": o.get("fulfillment_status"),
                "created_at": o.get("created_at"),
                "line_items_count": len(o.get("line_items", [])),
            }
            for o in orders
        ],
    }


def get_order(order_id: int) -> dict:
    """Get full order detail by ID."""
    return _get(f"/orders/{order_id}.json")


def order_count(status: str = "any") -> dict:
    """Get total order count."""
    return _get("/orders/count.json", {"status": status})


def orders_summary() -> dict:
    """Revenue summary — last 250 paid orders."""
    data = _get("/orders.json", {"limit": 250, "financial_status": "paid", "status": "any"})
    orders = data.get("orders", [])
    total_revenue = sum(float(o.get("total_price", 0)) for o in orders)
    return {
        "paid_orders_fetched": len(orders),
        "total_revenue_usd": round(total_revenue, 2),
        "average_order_value": round(total_revenue / len(orders), 2) if orders else 0,
    }


# ─────────────────────────────────────────────
# Customers
# ─────────────────────────────────────────────

def list_customers(limit: int = 50) -> dict:
    """List customers."""
    data = _get("/customers.json", {"limit": limit})
    customers = data.get("customers", [])
    return {
        "count": len(customers),
        "customers": [
            {
                "id": c["id"],
                "email": c.get("email"),
                "first_name": c.get("first_name"),
                "last_name": c.get("last_name"),
                "orders_count": c.get("orders_count"),
                "total_spent": c.get("total_spent"),
                "created_at": c.get("created_at"),
            }
            for c in customers
        ],
    }


def search_customers(query: str) -> dict:
    """Search customers by email, name, or phone."""
    data = _get("/customers/search.json", {"query": query, "limit": 25})
    return data


def customer_count() -> dict:
    """Total customer count."""
    return _get("/customers/count.json")


# ─────────────────────────────────────────────
# Inventory
# ─────────────────────────────────────────────

def list_locations() -> dict:
    """List all inventory locations."""
    return _get("/locations.json")


def inventory_levels(location_id: int, limit: int = 50) -> dict:
    """Get inventory levels for a specific location."""
    return _get("/inventory_levels.json", {"location_ids": location_id, "limit": limit})


def adjust_inventory(inventory_item_id: int, location_id: int, adjustment: int) -> dict:
    """Adjust inventory quantity at a location (positive or negative delta)."""
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available_adjustment": adjustment,
    }
    return _post("/inventory_levels/adjust.json", payload)


def set_inventory(inventory_item_id: int, location_id: int, available: int) -> dict:
    """Set exact inventory quantity at a location."""
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": available,
    }
    return _post("/inventory_levels/set.json", payload)


# ─────────────────────────────────────────────
# Themes
# ─────────────────────────────────────────────

def list_themes() -> dict:
    """List all installed themes."""
    data = _get("/themes.json")
    themes = data.get("themes", [])
    return {
        "count": len(themes),
        "themes": [
            {
                "id": t["id"],
                "name": t["name"],
                "role": t.get("role"),
                "created_at": t.get("created_at"),
                "updated_at": t.get("updated_at"),
            }
            for t in themes
        ],
    }


def get_theme_assets(theme_id: int) -> dict:
    """List all asset keys in a theme."""
    return _get(f"/themes/{theme_id}/assets.json")


def get_theme_asset(theme_id: int, asset_key: str) -> dict:
    """Get a single theme asset by key (e.g. 'layout/theme.liquid')."""
    return _get(f"/themes/{theme_id}/assets.json", {"asset[key]": asset_key})


def update_theme_asset(theme_id: int, asset_key: str, value: str) -> dict:
    """Update a theme asset with new string content."""
    payload = {"asset": {"key": asset_key, "value": value}}
    return _put(f"/themes/{theme_id}/assets.json", payload)


# ─────────────────────────────────────────────
# Content — Pages
# ─────────────────────────────────────────────

def list_pages(limit: int = 50) -> dict:
    """List all pages."""
    data = _get("/pages.json", {"limit": limit})
    pages = data.get("pages", [])
    return {
        "count": len(pages),
        "pages": [
            {
                "id": p["id"],
                "title": p["title"],
                "handle": p.get("handle"),
                "published_at": p.get("published_at"),
                "updated_at": p.get("updated_at"),
            }
            for p in pages
        ],
    }


def get_page(page_id: int) -> dict:
    """Get full page by ID."""
    return _get(f"/pages/{page_id}.json")


def create_page(title: str, body_html: str, published: bool = True) -> dict:
    """Create a new page."""
    payload = {"page": {"title": title, "body_html": body_html, "published": published}}
    return _post("/pages.json", payload)


def update_page(page_id: int, updates: dict) -> dict:
    """Update page fields."""
    payload = {"page": {"id": page_id, **updates}}
    return _put(f"/pages/{page_id}.json", payload)


def update_page_seo(page_id: int, seo_title: str, seo_description: str) -> dict:
    """Update SEO title and description for a page."""
    payload = {
        "page": {
            "id": page_id,
            "metafields_global_title_tag": seo_title,
            "metafields_global_description_tag": seo_description,
        }
    }
    return _put(f"/pages/{page_id}.json", payload)


# ─────────────────────────────────────────────
# Content — Blogs & Articles
# ─────────────────────────────────────────────

def list_blogs() -> dict:
    """List all blogs."""
    return _get("/blogs.json")


def list_articles(blog_id: int, limit: int = 50) -> dict:
    """List articles in a blog."""
    data = _get(f"/blogs/{blog_id}/articles.json", {"limit": limit})
    articles = data.get("articles", [])
    return {
        "count": len(articles),
        "articles": [
            {
                "id": a["id"],
                "title": a["title"],
                "author": a.get("author"),
                "published_at": a.get("published_at"),
                "tags": a.get("tags", ""),
            }
            for a in articles
        ],
    }


def create_article(blog_id: int, title: str, body_html: str,
                   author: str = "", tags: str = "",
                   published: bool = True) -> dict:
    """Create a new article in a blog."""
    payload = {
        "article": {
            "title": title,
            "body_html": body_html,
            "author": author,
            "tags": tags,
            "published": published,
        }
    }
    return _post(f"/blogs/{blog_id}/articles.json", payload)


def update_article(blog_id: int, article_id: int, updates: dict) -> dict:
    """Update an article."""
    payload = {"article": {"id": article_id, **updates}}
    return _put(f"/blogs/{blog_id}/articles/{article_id}.json", payload)


# ─────────────────────────────────────────────
# Price Rules & Discounts
# ─────────────────────────────────────────────

def list_price_rules(limit: int = 50) -> dict:
    """List all price rules (discount codes)."""
    data = _get("/price_rules.json", {"limit": limit})
    rules = data.get("price_rules", [])
    return {
        "count": len(rules),
        "price_rules": [
            {
                "id": r["id"],
                "title": r["title"],
                "value_type": r.get("value_type"),
                "value": r.get("value"),
                "usage_count": r.get("usage_count", 0),
                "starts_at": r.get("starts_at"),
                "ends_at": r.get("ends_at"),
            }
            for r in rules
        ],
    }


def create_price_rule(title: str, value_type: str, value: str,
                      customer_selection: str = "all",
                      target_type: str = "line_item",
                      target_selection: str = "all",
                      allocation_method: str = "across",
                      starts_at: str = "2024-01-01T00:00:00Z",
                      ends_at: Optional[str] = None) -> dict:
    """
    Create a price rule.
    value_type: 'percentage' or 'fixed_amount'
    value: negative string e.g. '-10.0' for 10% or $10 off
    """
    payload = {
        "price_rule": {
            "title": title,
            "value_type": value_type,
            "value": value,
            "customer_selection": customer_selection,
            "target_type": target_type,
            "target_selection": target_selection,
            "allocation_method": allocation_method,
            "starts_at": starts_at,
        }
    }
    if ends_at:
        payload["price_rule"]["ends_at"] = ends_at
    return _post("/price_rules.json", payload)


def list_discount_codes(price_rule_id: int) -> dict:
    """List discount codes for a price rule."""
    return _get(f"/price_rules/{price_rule_id}/discount_codes.json")


def create_discount_code(price_rule_id: int, code: str) -> dict:
    """Create a discount code under a price rule."""
    payload = {"discount_code": {"code": code}}
    return _post(f"/price_rules/{price_rule_id}/discount_codes.json", payload)


# ─────────────────────────────────────────────
# Metafields (global SEO + custom data)
# ─────────────────────────────────────────────

def list_metafields(owner_resource: str, owner_id: int) -> dict:
    """
    List metafields for any resource.
    owner_resource: 'product', 'page', 'collection', 'article', 'shop', etc.
    """
    return _get(f"/{owner_resource}s/{owner_id}/metafields.json")


def set_metafield(owner_resource: str, owner_id: int,
                  namespace: str, key: str, value: str,
                  type_: str = "single_line_text_field") -> dict:
    """Create or update a metafield on any resource."""
    payload = {
        "metafield": {
            "namespace": namespace,
            "key": key,
            "value": value,
            "type": type_,
        }
    }
    return _post(f"/{owner_resource}s/{owner_id}/metafields.json", payload)


# ─────────────────────────────────────────────
# Collections
# ─────────────────────────────────────────────

def list_custom_collections(limit: int = 50) -> dict:
    """List custom collections."""
    data = _get("/custom_collections.json", {"limit": limit})
    collections = data.get("custom_collections", [])
    return {
        "count": len(collections),
        "collections": [
            {
                "id": c["id"],
                "title": c["title"],
                "handle": c.get("handle"),
                "updated_at": c.get("updated_at"),
            }
            for c in collections
        ],
    }


def list_smart_collections(limit: int = 50) -> dict:
    """List smart (automated) collections."""
    data = _get("/smart_collections.json", {"limit": limit})
    collections = data.get("smart_collections", [])
    return {
        "count": len(collections),
        "collections": [
            {
                "id": c["id"],
                "title": c["title"],
                "handle": c.get("handle"),
                "rules_count": len(c.get("rules", [])),
                "updated_at": c.get("updated_at"),
            }
            for c in collections
        ],
    }


# ─────────────────────────────────────────────
# Store Overview (dashboard summary)
# ─────────────────────────────────────────────

def store_overview() -> dict:
    """
    High-level store health snapshot:
    product counts, order counts, customer counts.
    """
    try:
        products = _get("/products/count.json", {"status": "active"}).get("count", 0)
        orders_open = _get("/orders/count.json", {"status": "open"}).get("count", 0)
        orders_any = _get("/orders/count.json", {"status": "any"}).get("count", 0)
        customers = _get("/customers/count.json").get("count", 0)
        shop = _get("/shop.json").get("shop", {})
        return {
            "shop_name": shop.get("name"),
            "domain": shop.get("domain"),
            "plan": shop.get("plan_name"),
            "currency": shop.get("currency"),
            "active_products": products,
            "open_orders": orders_open,
            "total_orders": orders_any,
            "total_customers": customers,
        }
    except Exception as e:
        logger.error("store_overview error: %s", e)
        raise
