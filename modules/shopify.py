"""
Shopify Admin API module for GCP Bot.
Covers: Products, Orders, Customers, Inventory, Content (Pages/Blogs/Articles),
        Themes, Price Rules / Discounts, SEO meta patching,
        Fulfillments, Refunds, Webhooks, Abandoned Checkouts,
        Draft Orders, URL Redirects, Payouts (Shopify Payments),
        Analytics / Reports, Store Events,
        Carrier Services / Shipping Rates,
        Flow Automations (Shopify Flow),
        Shipping Profiles / Delivery Profiles (GraphQL only),
        Markets (GraphQL only).

All REST calls use the Admin REST API v2026-04.
All GraphQL calls use the Admin GraphQL API v2026-04.
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
GRAPHQL_URL = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{API_VERSION}/graphql.json"
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
        _env_token = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
        if _env_token:
            self._token: str = _env_token
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
# GraphQL Client
# ─────────────────────────────────────────────

def _graphql(query: str, variables: Optional[dict] = None) -> dict:
    """
    Execute a Shopify Admin GraphQL query or mutation.

    Args:
        query:     GraphQL query/mutation string.
        variables: Optional dict of GraphQL variables.

    Returns:
        The full parsed JSON response from Shopify (includes 'data' and
        optionally 'errors' keys). Raises requests.HTTPError on HTTP failures
        and RuntimeError if the response contains GraphQL-level errors.

    Notes:
        - Uses the same token cache as REST calls (_token_cache.get()).
        - All GraphQL calls share the same API_VERSION as REST (2026-04).
        - Shopify GraphQL is subject to cost-based rate limiting (query cost
          system). For bulk operations, use the bulkOperationRunQuery pattern
          instead of paginating with this function.
    """
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables

    r = requests.post(
        GRAPHQL_URL,
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    if "errors" in data:
        logger.error("GraphQL errors: %s", data["errors"])
        raise RuntimeError(f"Shopify GraphQL errors: {data['errors']}")

    return data


# ─────────────────────────────────────────────
# Health / Connection Test
# ─────────────────────────────────────────────

def token_status() -> dict:
    """Return current token cache status without making an API call."""
    return _token_cache.status()


def force_token_refresh() -> dict:
    """Force an immediate token refresh regardless of TTL."""
    with _token_cache._lock:
        _token_cache._expires_at = 0.0
    _token_cache.get()
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


def update_product_type(product_gid: str, product_type: str) -> dict:
    """Set productType on a product via productUpdate mutation."""
    mutation = """
    mutation updateProductType($input: ProductInput!) {
      productUpdate(input: $input) {
        product { id productType }
        userErrors { field message }
      }
    }
    """
    return _graphql(mutation, {"input": {"id": product_gid, "productType": product_type}})


def update_google_product_category(product_id: int, category_id: str) -> dict:
    """Write the google_product_category metafield on a product.

    category_id is the numeric Google taxonomy ID string (e.g. "212").
    This is read by Shopify's Google channel and surfaced to GMC as the
    google_product_category feed attribute.
    """
    return set_metafield(
        "product", product_id,
        namespace="google",
        key="google_product_category",
        value=category_id,
        type_="single_line_text_field",
    )


def update_variant_weight(variant_id: int, weight_g: float) -> dict:
    """Set weight (in grams) on a product variant via REST.

    variant_id is the numeric Shopify variant ID (not a GID).
    Only writes if the variant has no weight set (weight == 0 or null).
    Caller should check before invoking.
    """
    return _put(f"/variants/{variant_id}.json", {
        "variant": {"id": variant_id, "weight": weight_g, "weight_unit": "g"},
    })


def update_inventory_item_compliance(inv_item_gid: str, coo: str, hs_code: str) -> dict:
    """
    Set countryCodeOfOrigin and harmonizedSystemCode on an InventoryItem.

    Args:
        inv_item_gid: Full Shopify GID, e.g. "gid://shopify/InventoryItem/12345"
        coo:          ISO 3166-1 alpha-2 country code, e.g. "CN" or "US"
        hs_code:      6-digit HS code string, e.g. "610910"

    Returns the full GraphQL response dict.
    """
    mutation = """
    mutation inventoryItemUpdate($id: ID!, $input: InventoryItemUpdateInput!) {
      inventoryItemUpdate(id: $id, input: $input) {
        inventoryItem {
          id
          countryCodeOfOrigin
          harmonizedSystemCode
        }
        userErrors { field message }
      }
    }
    """
    return _graphql(mutation, {
        "id": inv_item_gid,
        "input": {
            "countryCodeOfOrigin": coo,
            "harmonizedSystemCode": hs_code,
        },
    })


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


# ─────────────────────────────────────────────
# Product Image Alt Text
# ─────────────────────────────────────────────

def update_product_image_alt(product_id: int, image_id: int, alt_text: str) -> dict:
    """
    Update the alt text for a specific product image.
    Used by the vision agent to write NIM-generated alt text back to Shopify.
    """
    payload = {
        "image": {
            "id":  image_id,
            "alt": alt_text,
        }
    }
    return _put(f"/products/{product_id}/images/{image_id}.json", payload)


def list_product_images(product_id: int) -> dict:
    """List all images for a product, including alt text and src."""
    return _get(f"/products/{product_id}/images.json")


# ─────────────────────────────────────────────
# Fulfillments
# ─────────────────────────────────────────────

def list_fulfillments(order_id: int) -> dict:
    """List all fulfillments for an order."""
    data = _get(f"/orders/{order_id}/fulfillments.json")
    fulfillments = data.get("fulfillments", [])
    return {
        "count": len(fulfillments),
        "fulfillments": [
            {
                "id": f["id"],
                "status": f.get("status"),
                "tracking_company": f.get("tracking_company"),
                "tracking_number": f.get("tracking_number"),
                "tracking_url": f.get("tracking_url"),
                "created_at": f.get("created_at"),
                "updated_at": f.get("updated_at"),
            }
            for f in fulfillments
        ],
    }


def create_fulfillment(order_id: int, location_id: int,
                       line_items: Optional[list] = None,
                       tracking_number: str = "",
                       tracking_company: str = "",
                       notify_customer: bool = True) -> dict:
    """
    Create a fulfillment for an order.
    line_items: list of {id, quantity} dicts. If None, fulfills all items.
    """
    fulfillment_payload: dict = {
        "location_id": location_id,
        "notify_customer": notify_customer,
    }
    if tracking_number:
        fulfillment_payload["tracking_info"] = {
            "number": tracking_number,
            "company": tracking_company,
        }
    if line_items:
        fulfillment_payload["line_items_by_fulfillment_order"] = line_items
    return _post(f"/orders/{order_id}/fulfillments.json", {"fulfillment": fulfillment_payload})


def cancel_fulfillment(order_id: int, fulfillment_id: int) -> dict:
    """Cancel a pending fulfillment."""
    return _post(f"/orders/{order_id}/fulfillments/{fulfillment_id}/cancel.json", {})


def update_fulfillment_tracking(order_id: int, fulfillment_id: int,
                                 tracking_number: str,
                                 tracking_company: str = "",
                                 notify_customer: bool = True) -> dict:
    """Update tracking info on an existing fulfillment."""
    payload = {
        "fulfillment": {
            "tracking_info": {
                "number": tracking_number,
                "company": tracking_company,
            },
            "notify_customer": notify_customer,
        }
    }
    return _put(f"/orders/{order_id}/fulfillments/{fulfillment_id}.json", payload)


# ─────────────────────────────────────────────
# Refunds
# ─────────────────────────────────────────────

def list_refunds(order_id: int) -> dict:
    """List all refunds for an order."""
    data = _get(f"/orders/{order_id}/refunds.json")
    refunds = data.get("refunds", [])
    return {
        "count": len(refunds),
        "refunds": [
            {
                "id": r["id"],
                "note": r.get("note"),
                "created_at": r.get("created_at"),
                "transactions": r.get("transactions", []),
                "refund_line_items": r.get("refund_line_items", []),
            }
            for r in refunds
        ],
    }


def calculate_refund(order_id: int, line_items: Optional[list] = None,
                     shipping: Optional[dict] = None) -> dict:
    """
    Calculate refund amounts before issuing.
    line_items: list of {line_item_id, quantity, restock_type} dicts.
    shipping: {full_refund: bool} or {amount: str}.
    """
    payload: dict = {}
    if line_items:
        payload["refund_line_items"] = [
            {"line_item_id": li["line_item_id"],
             "quantity": li["quantity"],
             "restock_type": li.get("restock_type", "no_restock")}
            for li in line_items
        ]
    if shipping:
        payload["shipping"] = shipping
    return _post(f"/orders/{order_id}/refunds/calculate.json", {"refund": payload})


def create_refund(order_id: int, note: str = "",
                  line_items: Optional[list] = None,
                  shipping: Optional[dict] = None,
                  transactions: Optional[list] = None) -> dict:
    """
    Issue a refund on an order.
    Recommended: run calculate_refund first to get exact amounts.
    transactions: list of {parent_id, amount, kind, gateway} dicts.
    """
    payload: dict = {"note": note, "notify": True}
    if line_items:
        payload["refund_line_items"] = line_items
    if shipping:
        payload["shipping"] = shipping
    if transactions:
        payload["transactions"] = transactions
    return _post(f"/orders/{order_id}/refunds.json", {"refund": payload})


# ─────────────────────────────────────────────
# Draft Orders
# ─────────────────────────────────────────────

def list_draft_orders(limit: int = 50, status: str = "any") -> dict:
    """List draft orders. status: open / invoice_sent / completed / any."""
    data = _get("/draft_orders.json", {"limit": limit, "status": status})
    drafts = data.get("draft_orders", [])
    return {
        "count": len(drafts),
        "draft_orders": [
            {
                "id": d["id"],
                "name": d.get("name"),
                "email": d.get("email"),
                "total_price": d.get("total_price"),
                "status": d.get("status"),
                "created_at": d.get("created_at"),
            }
            for d in drafts
        ],
    }


def get_draft_order(draft_order_id: int) -> dict:
    """Get full draft order detail."""
    return _get(f"/draft_orders/{draft_order_id}.json")


def create_draft_order(line_items: list,
                       email: str = "",
                       customer_id: Optional[int] = None,
                       note: str = "",
                       tags: str = "") -> dict:
    """
    Create a draft order.
    line_items: list of {variant_id, quantity} dicts.
    """
    payload: dict = {
        "draft_order": {
            "line_items": line_items,
            "note": note,
            "tags": tags,
        }
    }
    if email:
        payload["draft_order"]["email"] = email
    if customer_id:
        payload["draft_order"]["customer"] = {"id": customer_id}
    return _post("/draft_orders.json", payload)


def send_draft_order_invoice(draft_order_id: int,
                              from_email: str = "",
                              subject: str = "Your invoice from our store",
                              custom_message: str = "") -> dict:
    """Send the invoice email for a draft order."""
    payload = {
        "draft_order_invoice": {
            "to": "",
            "from": from_email,
            "subject": subject,
            "custom_message": custom_message,
        }
    }
    return _post(f"/draft_orders/{draft_order_id}/send_invoice.json", payload)


def complete_draft_order(draft_order_id: int, payment_pending: bool = False) -> dict:
    """Mark a draft order as complete (converts to a real order)."""
    return _put(
        f"/draft_orders/{draft_order_id}/complete.json",
        {"payment_pending": payment_pending},
    )


def delete_draft_order(draft_order_id: int) -> dict:
    """Delete a draft order."""
    return _delete(f"/draft_orders/{draft_order_id}.json")


# ─────────────────────────────────────────────
# Webhooks
# ─────────────────────────────────────────────

def list_webhooks() -> dict:
    """List all registered webhooks."""
    data = _get("/webhooks.json")
    hooks = data.get("webhooks", [])
    return {
        "count": len(hooks),
        "webhooks": [
            {
                "id": h["id"],
                "topic": h.get("topic"),
                "address": h.get("address"),
                "format": h.get("format"),
                "created_at": h.get("created_at"),
            }
            for h in hooks
        ],
    }


def create_webhook(topic: str, address: str, format_: str = "json") -> dict:
    """
    Register a new webhook.
    topic examples: 'orders/create', 'products/update', 'customers/create'
    address: your HTTPS endpoint URL.
    """
    payload = {
        "webhook": {
            "topic": topic,
            "address": address,
            "format": format_,
        }
    }
    return _post("/webhooks.json", payload)


def delete_webhook(webhook_id: int) -> dict:
    """Delete a webhook by ID."""
    return _delete(f"/webhooks/{webhook_id}.json")


def get_webhook(webhook_id: int) -> dict:
    """Get a single webhook by ID."""
    return _get(f"/webhooks/{webhook_id}.json")


# ─────────────────────────────────────────────
# Abandoned Checkouts
# ─────────────────────────────────────────────

def list_abandoned_checkouts(limit: int = 50,
                               since_id: Optional[int] = None) -> dict:
    """
    List abandoned checkouts.
    Useful for re-engagement campaigns.
    """
    params: dict = {"limit": limit}
    if since_id:
        params["since_id"] = since_id
    data = _get("/checkouts.json", params)
    checkouts = data.get("checkouts", [])
    return {
        "count": len(checkouts),
        "checkouts": [
            {
                "id": c["id"],
                "token": c.get("token"),
                "email": c.get("email"),
                "total_price": c.get("total_price"),
                "abandoned_checkout_url": c.get("abandoned_checkout_url"),
                "created_at": c.get("created_at"),
                "updated_at": c.get("updated_at"),
            }
            for c in checkouts
        ],
    }


# ─────────────────────────────────────────────
# URL Redirects
# ─────────────────────────────────────────────

def list_redirects(limit: int = 50) -> dict:
    """List all URL redirects."""
    data = _get("/redirects.json", {"limit": limit})
    redirects = data.get("redirects", [])
    return {
        "count": len(redirects),
        "redirects": [
            {
                "id": r["id"],
                "path": r.get("path"),
                "target": r.get("target"),
            }
            for r in redirects
        ],
    }


def create_redirect(path: str, target: str) -> dict:
    """Create a 301 URL redirect."""
    payload = {"redirect": {"path": path, "target": target}}
    return _post("/redirects.json", payload)


def delete_redirect(redirect_id: int) -> dict:
    """Delete a URL redirect."""
    return _delete(f"/redirects/{redirect_id}.json")


def count_redirects() -> dict:
    """Total redirect count."""
    return _get("/redirects/count.json")


# ─────────────────────────────────────────────
# Shopify Payments — Payouts
# ─────────────────────────────────────────────

def list_payouts(limit: int = 50, status: str = "paid") -> dict:
    """
    List Shopify Payments payouts.
    status: scheduled / in_transit / paid / failed / cancelled.
    Only available on stores using Shopify Payments.
    """
    data = _get("/shopify_payments/payouts.json", {"limit": limit, "status": status})
    payouts = data.get("payouts", [])
    return {
        "count": len(payouts),
        "payouts": [
            {
                "id": p["id"],
                "status": p.get("status"),
                "currency": p.get("currency"),
                "amount": p.get("amount"),
                "payout_date": p.get("date"),
            }
            for p in payouts
        ],
    }


def payout_transactions(payout_id: int, limit: int = 50) -> dict:
    """List all balance transactions in a payout."""
    return _get("/shopify_payments/balance/transactions.json",
                {"payout_id": payout_id, "limit": limit})


def payments_balance() -> dict:
    """Get current Shopify Payments account balance."""
    return _get("/shopify_payments/balance.json")


# ─────────────────────────────────────────────
# Analytics / Reports
# ─────────────────────────────────────────────

def list_reports(limit: int = 50) -> dict:
    """List all saved reports (requires Shopify Analytics access)."""
    data = _get("/reports.json", {"limit": limit})
    reports = data.get("reports", [])
    return {
        "count": len(reports),
        "reports": [
            {
                "id": r["id"],
                "name": r.get("name"),
                "shopify_ql": r.get("shopify_ql"),
                "updated_at": r.get("updated_at"),
            }
            for r in reports
        ],
    }


def get_report(report_id: int) -> dict:
    """Get a specific saved report."""
    return _get(f"/reports/{report_id}.json")


def create_report(name: str, shopify_ql: str) -> dict:
    """
    Create a custom ShopifyQL report.
    Example shopify_ql: 'SHOW total_sales BY day FROM 2024-01-01 TO 2024-12-31'
    """
    payload = {"report": {"name": name, "shopify_ql": shopify_ql}}
    return _post("/reports.json", payload)


# ─────────────────────────────────────────────
# Store Events (Activity Log)
# ─────────────────────────────────────────────

def list_events(limit: int = 50,
                verb: str = "",
                subject_type: str = "") -> dict:
    """
    List store events (audit log).
    verb examples: 'create', 'update', 'delete', 'publish'.
    subject_type: 'Order', 'Product', 'Customer', 'Collection', 'Page', etc.
    """
    params: dict = {"limit": limit}
    if verb:
        params["verb"] = verb
    if subject_type:
        params["filter"] = subject_type
    data = _get("/events.json", params)
    events = data.get("events", [])
    return {
        "count": len(events),
        "events": [
            {
                "id": e["id"],
                "subject_type": e.get("subject_type"),
                "subject_id": e.get("subject_id"),
                "verb": e.get("verb"),
                "message": e.get("message"),
                "created_at": e.get("created_at"),
            }
            for e in events
        ],
    }


def event_count(subject_type: str = "") -> dict:
    """Count store events, optionally filtered by subject_type."""
    params: dict = {}
    if subject_type:
        params["filter"] = subject_type
    return _get("/events/count.json", params)


# ─────────────────────────────────────────────
# Carrier Services & Shipping Rates
# ─────────────────────────────────────────────

def list_carrier_services() -> dict:
    """
    List all custom carrier services registered with the store.
    Carrier services power dynamic shipping rate callbacks to external URLs.
    Requires 'write_shipping' scope.
    """
    data = _get("/carrier_services.json")
    services = data.get("carrier_services", [])
    return {
        "count": len(services),
        "carrier_services": [
            {
                "id": s["id"],
                "name": s.get("name"),
                "callback_url": s.get("callback_url"),
                "service_discovery": s.get("service_discovery"),
                "carrier_service_type": s.get("carrier_service_type"),
                "active": s.get("active"),
                "format": s.get("format"),
            }
            for s in services
        ],
    }


def get_carrier_service(carrier_service_id: int) -> dict:
    """Get a specific carrier service by ID."""
    return _get(f"/carrier_services/{carrier_service_id}.json")


def create_carrier_service(name: str, callback_url: str,
                            service_discovery: bool = True,
                            carrier_service_type: str = "api",
                            format_: str = "json") -> dict:
    """
    Register a custom carrier service (dynamic rates via callback).
    callback_url: HTTPS endpoint Shopify will POST checkout data to for rates.
    service_discovery: if True, Shopify shows this carrier in the admin UI.
    carrier_service_type: 'api' (dynamic) or 'legacy'.
    Requires 'write_shipping' scope.
    """
    payload = {
        "carrier_service": {
            "name": name,
            "callback_url": callback_url,
            "service_discovery": service_discovery,
            "carrier_service_type": carrier_service_type,
            "format": format_,
            "active": True,
        }
    }
    return _post("/carrier_services.json", payload)


def update_carrier_service(carrier_service_id: int, updates: dict) -> dict:
    """
    Update a carrier service (e.g. change callback_url or toggle active).
    updates: dict of fields to change, e.g. {"active": False, "callback_url": "https://..."}
    """
    payload = {"carrier_service": {"id": carrier_service_id, **updates}}
    return _put(f"/carrier_services/{carrier_service_id}.json", payload)


def delete_carrier_service(carrier_service_id: int) -> dict:
    """Delete a carrier service. This removes the dynamic rate integration entirely."""
    return _delete(f"/carrier_services/{carrier_service_id}.json")


def list_shipping_zones() -> dict:
    """
    List all shipping zones and their associated rates.
    Each zone has price-based rates, weight-based rates, and carrier-calculated rates.
    Useful for auditing or displaying shipping options to customers.
    """
    data = _get("/shipping_zones.json")
    zones = data.get("shipping_zones", [])
    return {
        "count": len(zones),
        "shipping_zones": [
            {
                "id": z["id"],
                "name": z.get("name"),
                "countries": [c.get("name") for c in z.get("countries", [])],
                "price_based_shipping_rates": z.get("price_based_shipping_rates", []),
                "weight_based_shipping_rates": z.get("weight_based_shipping_rates", []),
                "carrier_shipping_rate_providers": z.get("carrier_shipping_rate_providers", []),
            }
            for z in zones
        ],
    }


def shipping_rates_summary() -> dict:
    """
    Summarise all shipping rates across all zones.
    Returns zone name, rate name, price, and min/max conditions for quick review.
    """
    data = _get("/shipping_zones.json")
    zones = data.get("shipping_zones", [])
    summary = []
    for z in zones:
        zone_name = z.get("name", "Unknown Zone")
        for rate in z.get("price_based_shipping_rates", []):
            summary.append({
                "zone": zone_name,
                "type": "price_based",
                "name": rate.get("name"),
                "price": rate.get("price"),
                "min_order_subtotal": rate.get("min_order_subtotal"),
                "max_order_subtotal": rate.get("max_order_subtotal"),
            })
        for rate in z.get("weight_based_shipping_rates", []):
            summary.append({
                "zone": zone_name,
                "type": "weight_based",
                "name": rate.get("name"),
                "price": rate.get("price"),
                "weight_low": rate.get("weight_low"),
                "weight_high": rate.get("weight_high"),
            })
        for rate in z.get("carrier_shipping_rate_providers", []):
            summary.append({
                "zone": zone_name,
                "type": "carrier_calculated",
                "carrier_service_id": rate.get("carrier_service_id"),
                "flat_modifier": rate.get("flat_modifier"),
                "percent_modifier": rate.get("percent_modifier"),
                "service_filter": rate.get("service_filter"),
            })
    return {"total_rates": len(summary), "rates": summary}


# ─────────────────────────────────────────────
# Flow Automations (Shopify Flow)
# ─────────────────────────────────────────────
# Shopify Flow is managed via the REST Admin API under /flow/ endpoints.
# These require the 'read_shopify_payments_payouts' or higher scope depending
# on plan. Flow is available on Shopify, Advanced, and Plus plans.
# ─────────────────────────────────────────────

def list_flows() -> dict:
    """
    List all Shopify Flow workflows.
    Returns id, title, enabled state, and trigger type for each workflow.
    Requires Shopify plan or higher (Flow not available on Basic).
    """
    data = _get("/flow/workflows.json")
    workflows = data.get("workflows", [])
    return {
        "count": len(workflows),
        "workflows": [
            {
                "id": w["id"],
                "title": w.get("title"),
                "enabled": w.get("enabled"),
                "created_at": w.get("created_at"),
                "updated_at": w.get("updated_at"),
            }
            for w in workflows
        ],
    }


def get_flow(workflow_id: int) -> dict:
    """Get full details of a specific Flow workflow by ID."""
    return _get(f"/flow/workflows/{workflow_id}.json")


def enable_flow(workflow_id: int) -> dict:
    """Enable a paused/disabled Flow workflow."""
    payload = {"workflow": {"id": workflow_id, "enabled": True}}
    return _put(f"/flow/workflows/{workflow_id}.json", payload)


def disable_flow(workflow_id: int) -> dict:
    """Disable (pause) a running Flow workflow without deleting it."""
    payload = {"workflow": {"id": workflow_id, "enabled": False}}
    return _put(f"/flow/workflows/{workflow_id}.json", payload)


def trigger_flow(workflow_id: int, payload: Optional[dict] = None) -> dict:
    """
    Trigger a Flow workflow that uses a 'trigger_run' or custom-trigger topic.
    payload: optional dict of custom properties to pass into the workflow context.
    Note: Only works for workflows with a compatible trigger type (e.g. custom trigger).
    """
    body: dict = {"workflow_trigger": {"workflow_id": workflow_id}}
    if payload:
        body["workflow_trigger"]["properties"] = payload
    return _post("/flow/triggers.json", body)


def list_flow_trigger_definitions() -> dict:
    """
    List all available Flow trigger definitions.
    Useful for understanding what events can kick off a Flow (e.g. order_created,
    customer_created, inventory_quantity_changed, custom).
    """
    return _get("/flow/trigger_definitions.json")


def list_flow_action_definitions() -> dict:
    """
    List all available Flow action definitions.
    Shows what actions are available in this store's Flow (e.g. add_tags,
    send_http_request, add_to_segment, send_email via partner apps).
    """
    return _get("/flow/action_definitions.json")


# ─────────────────────────────────────────────
# Shipping Profiles / Delivery Profiles (GraphQL)
# ─────────────────────────────────────────────
# DeliveryProfile is GraphQL-only — not available on the REST Admin API.
# These functions use _graphql() and require the 'read_shipping' scope.
#
# What a DeliveryProfile tells you:
#   - Profile name + whether it is the store's default (General) profile
#   - Which products are assigned to this profile (profileItems)
#   - Which locations fulfil orders from this profile (locationGroups)
#   - Which shipping zones + countries those locations cover
#   - Which shipping methods (rates) are active in each zone
#
# Audit checklist the bot runs automatically in audit_shipping_profiles():
#   ✓ Every active product is assigned to at least one profile
#   ✓ No product appears in multiple profiles (duplicate assignment)
#   ✓ Every profile has at least one active shipping method per zone
#   ✓ Every profile has at least one fulfillment location attached
#   ✓ The default (General) profile exists
# ─────────────────────────────────────────────

_DELIVERY_PROFILES_QUERY = """
query deliveryProfiles($first: Int!, $after: String) {
  deliveryProfiles(first: $first, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      name
      default
      profileLocationGroups {
        locationGroup {
          locations(first: 20) {
            nodes {
              id
              name
              isActive
            }
          }
        }
        locationGroupZones(first: 20) {
          nodes {
            zone {
              id
              name
              countries {
                name
                code {
                  countryCode
                }
              }
            }
            methodDefinitions(first: 20) {
              nodes {
                id
                name
                active
                rateProvider {
                  ... on DeliveryRateDefinition {
                    price {
                      amount
                      currencyCode
                    }
                  }
                  ... on DeliveryParticipant {
                    participantService {
                      name
                    }
                    fixedFee {
                      amount
                      currencyCode
                    }
                    percentageFee
                  }
                }
              }
            }
          }
        }
      }
      profileItems(first: 50) {
        nodes {
          product {
            id
            title
            status
          }
        }
      }
    }
  }
}
"""


def list_shipping_profiles(profiles_per_page: int = 10) -> dict:
    """
    List all delivery profiles using the GraphQL Admin API.

    Returns a structured dict with:
      - count: total number of profiles fetched
      - profiles: list of profiles, each with:
          - id, name, default (bool)
          - locations: active fulfillment locations attached to this profile
          - zones: shipping zones with countries and active method counts
          - products: products assigned to this profile (up to 50 per profile)

    Automatically paginates through all profiles.
    Requires 'read_shipping' OAuth scope.
    """
    profiles = []
    cursor = None
    has_next = True

    while has_next:
        variables: dict = {"first": profiles_per_page}
        if cursor:
            variables["after"] = cursor

        result = _graphql(_DELIVERY_PROFILES_QUERY, variables)
        connection = result["data"]["deliveryProfiles"]
        page_info = connection["pageInfo"]

        for node in connection["nodes"]:
            # Flatten locations from all location groups
            locations = []
            zones = []
            for lg in node.get("profileLocationGroups", []):
                for loc in lg["locationGroup"]["locations"]["nodes"]:
                    locations.append({
                        "id": loc["id"],
                        "name": loc["name"],
                        "is_active": loc["isActive"],
                    })
                for lgz in lg["locationGroupZones"]["nodes"]:
                    zone = lgz["zone"]
                    methods = lgz["methodDefinitions"]["nodes"]
                    active_methods = [m for m in methods if m.get("active")]
                    zones.append({
                        "id": zone["id"],
                        "name": zone["name"],
                        "countries": [
                            c["name"] for c in zone.get("countries", [])
                        ],
                        "total_methods": len(methods),
                        "active_methods": len(active_methods),
                        "method_names": [m["name"] for m in active_methods],
                    })

            # Flatten assigned products
            products = [
                {
                    "id": item["product"]["id"],
                    "title": item["product"]["title"],
                    "status": item["product"]["status"],
                }
                for item in node["profileItems"]["nodes"]
                if item.get("product")
            ]

            profiles.append({
                "id": node["id"],
                "name": node["name"],
                "is_default": node.get("default", False),
                "locations": locations,
                "zones": zones,
                "assigned_products": products,
                "assigned_products_count": len(products),
            })

        has_next = page_info["hasNextPage"]
        cursor = page_info.get("endCursor")

    return {
        "count": len(profiles),
        "profiles": profiles,
    }


def audit_shipping_profiles() -> dict:
    """
    Run a full health audit of all delivery profiles.

    Checks performed:
      1. Default (General) profile exists
      2. Every profile has at least one active fulfillment location
      3. Every profile has at least one shipping zone configured
      4. Every zone in every profile has at least one active rate method
      5. No product appears assigned to multiple profiles (duplicate detection)
      6. Active products not assigned to any profile (unshipped products)

    Returns:
      - passed (bool): True only if ALL checks pass
      - summary: human-readable list of findings
      - issues: structured list of {severity, profile, message} dicts
      - profiles_audited: count of profiles checked
      - unassigned_active_products: list of active product titles with no profile
      - duplicate_assignments: list of product titles in more than one profile
    """
    profiles_data = list_shipping_profiles()
    profiles = profiles_data["profiles"]

    issues = []
    summary = []

    # ── Check 1: Default profile exists ──
    default_profiles = [p for p in profiles if p["is_default"]]
    if not default_profiles:
        issues.append({
            "severity": "critical",
            "profile": "store",
            "message": "No default (General) shipping profile found. Every store must have one.",
        })
    else:
        summary.append(f"✓ Default profile exists: '{default_profiles[0]['name']}'")

    # ── Check 2: Every profile has at least one active location ──
    for p in profiles:
        active_locs = [l for l in p["locations"] if l["is_active"]]
        if not active_locs:
            issues.append({
                "severity": "critical",
                "profile": p["name"],
                "message": f"Profile '{p['name']}' has no active fulfillment locations attached.",
            })
        else:
            summary.append(
                f"✓ '{p['name']}': {len(active_locs)} active location(s) — "
                + ", ".join(l["name"] for l in active_locs)
            )

    # ── Check 3: Every profile has at least one zone ──
    for p in profiles:
        if not p["zones"]:
            issues.append({
                "severity": "warning",
                "profile": p["name"],
                "message": f"Profile '{p['name']}' has no shipping zones configured.",
            })
        else:
            summary.append(f"✓ '{p['name']}': {len(p['zones'])} zone(s) configured")

    # ── Check 4: Every zone has at least one active rate ──
    for p in profiles:
        for z in p["zones"]:
            if z["active_methods"] == 0:
                issues.append({
                    "severity": "critical",
                    "profile": p["name"],
                    "message": (
                        f"Zone '{z['name']}' in profile '{p['name']}' "
                        f"has {z['total_methods']} rate(s) but NONE are active. "
                        "Customers in this zone will see no shipping options at checkout."
                    ),
                })
            else:
                summary.append(
                    f"✓ '{p['name']}' → zone '{z['name']}': "
                    f"{z['active_methods']} active rate(s): {', '.join(z['method_names'])}"
                )

    # ── Check 5: Duplicate product assignments ──
    product_profile_map: dict = {}  # product_id → list of profile names
    for p in profiles:
        for prod in p["assigned_products"]:
            pid = prod["id"]
            if pid not in product_profile_map:
                product_profile_map[pid] = {"title": prod["title"], "profiles": []}
            product_profile_map[pid]["profiles"].append(p["name"])

    duplicates = [
        v for v in product_profile_map.values()
        if len(v["profiles"]) > 1
    ]
    if duplicates:
        for dup in duplicates:
            issues.append({
                "severity": "warning",
                "profile": ", ".join(dup["profiles"]),
                "message": (
                    f"Product '{dup['title']}' is assigned to multiple profiles: "
                    + ", ".join(dup["profiles"])
                    + ". Only the most specific profile will apply."
                ),
            })
    else:
        summary.append("✓ No duplicate product-to-profile assignments detected")

    # ── Check 6: Active products not in any profile ──
    # Pull active products from REST and cross-reference
    try:
        active_products_data = _get("/products.json", {"status": "active", "limit": 250})
        active_products = active_products_data.get("products", [])
        assigned_gids = {prod["id"] for prod in product_profile_map}

        # Shopify GID format: "gid://shopify/Product/123456789"
        unassigned = []
        for ap in active_products:
            gid = f"gid://shopify/Product/{ap['id']}"
            if gid not in assigned_gids:
                unassigned.append(ap["title"])

        if unassigned:
            issues.append({
                "severity": "warning",
                "profile": "General (default)",
                "message": (
                    f"{len(unassigned)} active product(s) have no explicit profile assignment "
                    "and will fall back to the General profile. "
                    f"Products: {', '.join(unassigned[:10])}"
                    + (" (+ more)" if len(unassigned) > 10 else "")
                ),
            })
            summary.append(
                f"⚠ {len(unassigned)} active product(s) rely on General profile fallback"
            )
        else:
            summary.append("✓ All active products have explicit profile assignments")
    except Exception as e:
        logger.warning("Could not cross-reference active products: %s", e)
        unassigned = []

    # ── Result ──
    critical_issues = [i for i in issues if i["severity"] == "critical"]
    warning_issues = [i for i in issues if i["severity"] == "warning"]

    return {
        "passed": len(critical_issues) == 0,
        "profiles_audited": len(profiles),
        "critical_issues": len(critical_issues),
        "warnings": len(warning_issues),
        "issues": issues,
        "summary": summary,
        "unassigned_active_products": unassigned,
        "duplicate_assignments": [d["title"] for d in duplicates],
    }


def get_shipping_profile(profile_gid: str) -> dict:
    """
    Get full detail for a single delivery profile by its GraphQL GID.
    profile_gid format: 'gid://shopify/DeliveryProfile/123456789'

    Use list_shipping_profiles() first to find the GID for the profile you want.
    """
    query = """
    query getDeliveryProfile($id: ID!) {
      deliveryProfile(id: $id) {
        id
        name
        default
        profileLocationGroups {
          locationGroup {
            locations(first: 20) {
              nodes { id name isActive }
            }
          }
          locationGroupZones(first: 20) {
            nodes {
              zone {
                id
                name
                countries { name code { countryCode } }
              }
              methodDefinitions(first: 20) {
                nodes {
                  id
                  name
                  active
                  rateProvider {
                    ... on DeliveryRateDefinition {
                      price { amount currencyCode }
                    }
                    ... on DeliveryParticipant {
                      participantService { name }
                      fixedFee { amount currencyCode }
                      percentageFee
                    }
                  }
                }
              }
            }
          }
        }
        profileItems(first: 50) {
          nodes {
            product { id title status }
          }
        }
      }
    }
    """
    result = _graphql(query, {"id": profile_gid})
    return result.get("data", {}).get("deliveryProfile", {})


# ─────────────────────────────────────────────
# Markets (GraphQL only)
# ─────────────────────────────────────────────
# Shopify Markets is GraphQL-only — there is no REST endpoint for markets.
# Markets control which countries/regions you sell to, what currency/language
# is presented, and which domain or subfolder serves each market.
#
# What a Market tells you:
#   - Market name + whether it is the primary (default) market
#   - enabled: whether the market is live and accepting orders
#   - regions: countries/sub-regions included in this market
#   - web presence: domain or subfolder + locale used for this market
#   - currencySettings: presentment currency and auto-rate vs fixed-rate
#   - metafields: any custom data attached to the market
#
# Audit checklist run automatically in audit_markets():
#   ✓ Primary market exists and is enabled
#   ✓ No market is disabled while having regions assigned to it
#   ✓ Every enabled market has at least one region
#   ✓ Every enabled market has a web presence configured (domain or subfolder)
#   ✓ No region appears in more than one market (duplicate region)
#   ✓ Currency settings are explicitly configured (not left to Shopify default)
# ─────────────────────────────────────────────

_MARKETS_QUERY = """
query listMarkets($first: Int!, $after: String) {
  markets(first: $first, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      name
      handle
      enabled
      primary
      createdAt
      updatedAt
      regions(first: 50) {
        nodes {
          __typename
          ... on MarketRegionCountry {
            name
            code
          }
        }
      }
      webPresence {
        domain {
          host
          sslEnabled
        }
        subfolderSuffix
        defaultLocale
        alternateLocales
        rootUrls {
          locale
          url
        }
      }
      currencySettings {
        baseCurrency {
          currencyCode
          currencyName
        }
        localCurrencies
        autoRate
        conversionRateToPresentmentCurrency
      }
    }
  }
}
"""


def list_markets(markets_per_page: int = 20) -> dict:
    """
    List all Shopify Markets using the GraphQL Admin API.

    Returns a structured dict with:
      - count: total number of markets
      - markets: list of markets, each with:
          - id, name, handle, enabled, primary (bool)
          - regions: list of {name, code} country dicts
          - web_presence: domain host or subfolder + locale info
          - currency: base currency code and whether local currencies are enabled
          - created_at, updated_at

    Automatically paginates through all markets.
    Requires 'read_markets' OAuth scope (available on all plans).
    """
    markets = []
    cursor = None
    has_next = True

    while has_next:
        variables: dict = {"first": markets_per_page}
        if cursor:
            variables["after"] = cursor

        result = _graphql(_MARKETS_QUERY, variables)
        connection = result["data"]["markets"]
        page_info = connection["pageInfo"]

        for node in connection["nodes"]:
            # Flatten regions
            regions = [
                {"name": r["name"], "code": r["code"]}
                for r in node["regions"]["nodes"]
                if r.get("__typename") == "MarketRegionCountry"
            ]

            # Flatten web presence
            wp = node.get("webPresence") or {}
            domain_host = None
            ssl_enabled = None
            if wp.get("domain"):
                domain_host = wp["domain"].get("host")
                ssl_enabled = wp["domain"].get("sslEnabled")

            # Flatten currency settings
            cs = node.get("currencySettings") or {}
            base_currency = None
            if cs.get("baseCurrency"):
                base_currency = cs["baseCurrency"].get("currencyCode")

            markets.append({
                "id": node["id"],
                "name": node["name"],
                "handle": node.get("handle"),
                "enabled": node.get("enabled", False),
                "primary": node.get("primary", False),
                "regions": regions,
                "regions_count": len(regions),
                "web_presence": {
                    "domain": domain_host,
                    "ssl_enabled": ssl_enabled,
                    "subfolder": wp.get("subfolderSuffix"),
                    "default_locale": wp.get("defaultLocale"),
                    "alternate_locales": wp.get("alternateLocales", []),
                    "root_urls": wp.get("rootUrls", []),
                },
                "currency": {
                    "base_currency": base_currency,
                    "local_currencies_enabled": cs.get("localCurrencies", False),
                    "auto_rate": cs.get("autoRate"),
                    "conversion_rate": cs.get("conversionRateToPresentmentCurrency"),
                },
                "created_at": node.get("createdAt"),
                "updated_at": node.get("updatedAt"),
            })

        has_next = page_info["hasNextPage"]
        cursor = page_info.get("endCursor")

    return {
        "count": len(markets),
        "markets": markets,
    }


def get_market(market_gid: str) -> dict:
    """
    Get full details for a single market by its GraphQL GID.
    market_gid format: 'gid://shopify/Market/123456789'

    Use list_markets() first to find the GID for the market you want.
    Requires 'read_markets' OAuth scope.
    """
    query = """
    query getMarket($id: ID!) {
      market(id: $id) {
        id
        name
        handle
        enabled
        primary
        createdAt
        updatedAt
        regions(first: 50) {
          nodes {
            __typename
            ... on MarketRegionCountry {
              name
              code
            }
          }
        }
        webPresence {
          domain { host sslEnabled }
          subfolderSuffix
          defaultLocale
          alternateLocales
          rootUrls { locale url }
        }
        currencySettings {
          baseCurrency { currencyCode currencyName }
          localCurrencies
          autoRate
          conversionRateToPresentmentCurrency
        }
      }
    }
    """
    result = _graphql(query, {"id": market_gid})
    return result.get("data", {}).get("market", {})


def audit_markets() -> dict:
    """
    Run a full health audit of all Shopify Markets.

    Checks performed:
      1. Primary market exists and is enabled
      2. No enabled market has zero regions assigned
      3. No disabled market has regions (orphaned regions)
      4. Every enabled market has a web presence (domain or subfolder)
      5. Every enabled non-primary market has SSL enabled on its domain
      6. No region (country code) appears in more than one market
      7. Currency settings are explicitly set on each market

    Returns:
      - passed (bool): True only if ALL critical checks pass
      - markets_audited: count of markets checked
      - critical_issues: count of critical findings
      - warnings: count of warning-level findings
      - issues: list of {severity, market, message} dicts
      - summary: human-readable list of ✓/⚠/✗ findings
      - duplicate_regions: list of country codes appearing in multiple markets
    """
    markets_data = list_markets()
    markets = markets_data["markets"]

    issues = []
    summary = []

    # ── Check 1: Primary market exists and is enabled ──
    primary_markets = [m for m in markets if m["primary"]]
    if not primary_markets:
        issues.append({
            "severity": "critical",
            "market": "store",
            "message": "No primary market found. Every Shopify store must have exactly one primary market.",
        })
    elif not primary_markets[0]["enabled"]:
        issues.append({
            "severity": "critical",
            "market": primary_markets[0]["name"],
            "message": f"Primary market '{primary_markets[0]['name']}' exists but is DISABLED. Customers may not be able to check out.",
        })
    else:
        summary.append(f"✓ Primary market: '{primary_markets[0]['name']}' — enabled")

    # ── Check 2: Enabled markets have at least one region ──
    for m in markets:
        if m["enabled"] and m["regions_count"] == 0:
            issues.append({
                "severity": "critical",
                "market": m["name"],
                "message": f"Market '{m['name']}' is enabled but has NO regions assigned. No customers will be routed to it.",
            })
        elif m["enabled"]:
            region_names = ", ".join(r["name"] for r in m["regions"][:5])
            extra = f" (+{m['regions_count'] - 5} more)" if m["regions_count"] > 5 else ""
            summary.append(f"✓ '{m['name']}': {m['regions_count']} region(s) — {region_names}{extra}")

    # ── Check 3: Disabled markets with regions (orphaned) ──
    for m in markets:
        if not m["enabled"] and m["regions_count"] > 0:
            issues.append({
                "severity": "warning",
                "market": m["name"],
                "message": (
                    f"Market '{m['name']}' is DISABLED but still has {m['regions_count']} region(s) assigned. "
                    "These regions are unreachable. Either enable the market or remove the regions."
                ),
            })

    # ── Check 4: Enabled markets have a web presence ──
    for m in markets:
        if not m["enabled"]:
            continue
        wp = m["web_presence"]
        has_domain = bool(wp.get("domain"))
        has_subfolder = bool(wp.get("subfolder"))
        if not has_domain and not has_subfolder:
            issues.append({
                "severity": "critical",
                "market": m["name"],
                "message": (
                    f"Market '{m['name']}' is enabled but has NO web presence configured "
                    "(no domain and no subfolder). Customers cannot reach this market's storefront."
                ),
            })
        else:
            presence = wp["domain"] if has_domain else f"/{wp['subfolder']}"
            locale = wp.get("default_locale", "unknown locale")
            summary.append(f"✓ '{m['name']}': web presence → {presence} ({locale})")

    # ── Check 5: SSL on custom domains ──
    for m in markets:
        if not m["enabled"]:
            continue
        wp = m["web_presence"]
        if wp.get("domain") and wp.get("ssl_enabled") is False:
            issues.append({
                "severity": "critical",
                "market": m["name"],
                "message": (
                    f"Market '{m['name']}' uses domain '{wp['domain']}' but SSL is NOT enabled. "
                    "Checkout will be blocked on this domain."
                ),
            })
        elif wp.get("domain") and wp.get("ssl_enabled"):
            summary.append(f"✓ '{m['name']}': SSL enabled on {wp['domain']}")

    # ── Check 6: Duplicate regions across markets ──
    region_market_map: dict = {}  # country_code → list of market names
    for m in markets:
        for region in m["regions"]:
            code = region["code"]
            if code not in region_market_map:
                region_market_map[code] = []
            region_market_map[code].append(m["name"])

    duplicate_regions = []
    for code, mkt_names in region_market_map.items():
        if len(mkt_names) > 1:
            duplicate_regions.append(code)
            issues.append({
                "severity": "warning",
                "market": ", ".join(mkt_names),
                "message": (
                    f"Country '{code}' is assigned to multiple markets: {', '.join(mkt_names)}. "
                    "Shopify uses the most specific match, but this may cause unexpected routing."
                ),
            })

    if not duplicate_regions:
        summary.append("✓ No duplicate country assignments across markets")

    # ── Check 7: Currency settings explicitly configured ──
    for m in markets:
        if not m["enabled"]:
            continue
        if not m["currency"].get("base_currency"):
            issues.append({
                "severity": "warning",
                "market": m["name"],
                "message": (
                    f"Market '{m['name']}' has no explicit base currency set. "
                    "It will inherit the store's default currency, which may not be correct for this market."
                ),
            })
        else:
            currency = m["currency"]["base_currency"]
            local = "local currencies ON" if m["currency"]["local_currencies_enabled"] else "local currencies OFF"
            summary.append(f"✓ '{m['name']}': currency = {currency}, {local}")

    # ── Result ──
    critical_issues = [i for i in issues if i["severity"] == "critical"]
    warning_issues = [i for i in issues if i["severity"] == "warning"]

    return {
        "passed": len(critical_issues) == 0,
        "markets_audited": len(markets),
        "critical_issues": len(critical_issues),
        "warnings": len(warning_issues),
        "issues": issues,
        "summary": summary,
        "duplicate_regions": duplicate_regions,
    }
