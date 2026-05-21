"""
Shopify Admin API — FastAPI router for GCP Bot.
All endpoints require DASHBOARD_API_KEY authentication.

Prefix: /api/shopify
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from modules import shopify as sh

logger = logging.getLogger("gcp-bot.routers.shopify")
router = APIRouter()


# ─────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────

class CreateProductRequest(BaseModel):
    title: str
    body_html: str = ""
    vendor: str = ""
    product_type: str = ""
    tags: str = ""
    status: str = "draft"


class UpdateProductRequest(BaseModel):
    updates: dict


class ProductSEORequest(BaseModel):
    seo_title: str
    seo_description: str


class CreatePageRequest(BaseModel):
    title: str
    body_html: str
    published: bool = True


class UpdatePageRequest(BaseModel):
    updates: dict


class PageSEORequest(BaseModel):
    seo_title: str
    seo_description: str


class CreateArticleRequest(BaseModel):
    title: str
    body_html: str
    author: str = ""
    tags: str = ""
    published: bool = True


class UpdateArticleRequest(BaseModel):
    updates: dict


class CreatePriceRuleRequest(BaseModel):
    title: str
    value_type: str          # 'percentage' or 'fixed_amount'
    value: str               # negative e.g. '-10.0'
    customer_selection: str = "all"
    target_type: str = "line_item"
    target_selection: str = "all"
    allocation_method: str = "across"
    starts_at: str = "2024-01-01T00:00:00Z"
    ends_at: Optional[str] = None


class CreateDiscountCodeRequest(BaseModel):
    code: str


class AdjustInventoryRequest(BaseModel):
    inventory_item_id: int
    location_id: int
    adjustment: int


class SetInventoryRequest(BaseModel):
    inventory_item_id: int
    location_id: int
    available: int


class UpdateThemeAssetRequest(BaseModel):
    asset_key: str
    value: str


class SetMetafieldRequest(BaseModel):
    owner_resource: str   # 'product', 'page', 'collection', etc.
    owner_id: int
    namespace: str
    key: str
    value: str
    type_: str = "single_line_text_field"


# ─────────────────────────────────────────────
# System / Connection
# ─────────────────────────────────────────────

@router.get("/token/status", summary="Token cache status (no API call)")
def token_status():
    """Returns TTL, expiry time, and next auto-refresh window for the admin token."""
    try:
        return sh.token_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/token/refresh", summary="Force immediate token refresh")
def force_token_refresh():
    """Immediately discard the cached token and fetch a fresh one via Client Credentials Grant."""
    try:
        return sh.force_token_refresh()
    except Exception as e:
        logger.error("Force token refresh failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/ping", summary="Test Shopify admin token connection")
def shopify_ping():
    """Verify admin token and return shop info (includes token_status)."""
    try:
        return sh.test_connection()
    except Exception as e:
        logger.error("Shopify ping failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/overview", summary="Store health snapshot")
def store_overview():
    """Products, orders, customers counts + shop metadata."""
    try:
        return sh.store_overview()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─────────────────────────────────────────────
# Products
# ─────────────────────────────────────────────

@router.get("/products", summary="List products")
def list_products(
    limit: int = Query(50, ge=1, le=250),
    status: str = Query("any", description="active | draft | archived | any"),
):
    try:
        return sh.list_products(limit=limit, status=status)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/products/count", summary="Product count")
def product_count(status: str = Query("any")):
    try:
        return sh.product_count(status=status)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/products/{product_id}", summary="Get product by ID")
def get_product(product_id: int):
    try:
        return sh.get_product(product_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/products", summary="Create product")
def create_product(req: CreateProductRequest):
    try:
        return sh.create_product(
            title=req.title,
            body_html=req.body_html,
            vendor=req.vendor,
            product_type=req.product_type,
            tags=req.tags,
            status=req.status,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.put("/products/{product_id}", summary="Update product")
def update_product(product_id: int, req: UpdateProductRequest):
    try:
        return sh.update_product(product_id, req.updates)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.put("/products/{product_id}/seo", summary="Update product SEO meta")
def update_product_seo(product_id: int, req: ProductSEORequest):
    try:
        return sh.update_product_seo(product_id, req.seo_title, req.seo_description)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─────────────────────────────────────────────
# Orders
# ─────────────────────────────────────────────

@router.get("/orders", summary="List orders")
def list_orders(
    limit: int = Query(50, ge=1, le=250),
    status: str = Query("any"),
    financial_status: str = Query("any"),
):
    try:
        return sh.list_orders(limit=limit, status=status,
                              financial_status=financial_status)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/orders/count", summary="Order count")
def order_count(status: str = Query("any")):
    try:
        return sh.order_count(status=status)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/orders/summary", summary="Revenue summary (last 250 paid orders)")
def orders_summary():
    try:
        return sh.orders_summary()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/orders/{order_id}", summary="Get order by ID")
def get_order(order_id: int):
    try:
        return sh.get_order(order_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─────────────────────────────────────────────
# Customers
# ─────────────────────────────────────────────

@router.get("/customers", summary="List customers")
def list_customers(limit: int = Query(50, ge=1, le=250)):
    try:
        return sh.list_customers(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/customers/count", summary="Customer count")
def customer_count():
    try:
        return sh.customer_count()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/customers/search", summary="Search customers")
def search_customers(q: str = Query(..., description="Email, name, or phone")):
    try:
        return sh.search_customers(q)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─────────────────────────────────────────────
# Inventory
# ─────────────────────────────────────────────

@router.get("/locations", summary="List inventory locations")
def list_locations():
    try:
        return sh.list_locations()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/inventory", summary="Inventory levels for a location")
def inventory_levels(
    location_id: int = Query(...),
    limit: int = Query(50),
):
    try:
        return sh.inventory_levels(location_id=location_id, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/inventory/adjust", summary="Adjust inventory quantity")
def adjust_inventory(req: AdjustInventoryRequest):
    try:
        return sh.adjust_inventory(
            req.inventory_item_id, req.location_id, req.adjustment
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/inventory/set", summary="Set exact inventory quantity")
def set_inventory(req: SetInventoryRequest):
    try:
        return sh.set_inventory(
            req.inventory_item_id, req.location_id, req.available
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─────────────────────────────────────────────
# Themes
# ─────────────────────────────────────────────

@router.get("/themes", summary="List installed themes")
def list_themes():
    try:
        return sh.list_themes()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/themes/{theme_id}/assets", summary="List all theme assets")
def get_theme_assets(theme_id: int):
    try:
        return sh.get_theme_assets(theme_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/themes/{theme_id}/asset", summary="Get a single theme asset")
def get_theme_asset(
    theme_id: int,
    asset_key: str = Query(..., description="e.g. layout/theme.liquid"),
):
    try:
        return sh.get_theme_asset(theme_id, asset_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.put("/themes/{theme_id}/asset", summary="Update a theme asset")
def update_theme_asset(theme_id: int, req: UpdateThemeAssetRequest):
    try:
        return sh.update_theme_asset(theme_id, req.asset_key, req.value)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─────────────────────────────────────────────
# Content — Pages
# ─────────────────────────────────────────────

@router.get("/pages", summary="List pages")
def list_pages(limit: int = Query(50, ge=1, le=250)):
    try:
        return sh.list_pages(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/pages/{page_id}", summary="Get page by ID")
def get_page(page_id: int):
    try:
        return sh.get_page(page_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/pages", summary="Create page")
def create_page(req: CreatePageRequest):
    try:
        return sh.create_page(req.title, req.body_html, req.published)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.put("/pages/{page_id}", summary="Update page")
def update_page(page_id: int, req: UpdatePageRequest):
    try:
        return sh.update_page(page_id, req.updates)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.put("/pages/{page_id}/seo", summary="Update page SEO meta")
def update_page_seo(page_id: int, req: PageSEORequest):
    try:
        return sh.update_page_seo(page_id, req.seo_title, req.seo_description)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─────────────────────────────────────────────
# Content — Blogs & Articles
# ─────────────────────────────────────────────

@router.get("/blogs", summary="List blogs")
def list_blogs():
    try:
        return sh.list_blogs()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/blogs/{blog_id}/articles", summary="List articles in a blog")
def list_articles(blog_id: int, limit: int = Query(50)):
    try:
        return sh.list_articles(blog_id, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/blogs/{blog_id}/articles", summary="Create article")
def create_article(blog_id: int, req: CreateArticleRequest):
    try:
        return sh.create_article(
            blog_id, req.title, req.body_html,
            req.author, req.tags, req.published
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.put("/blogs/{blog_id}/articles/{article_id}", summary="Update article")
def update_article(blog_id: int, article_id: int, req: UpdateArticleRequest):
    try:
        return sh.update_article(blog_id, article_id, req.updates)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─────────────────────────────────────────────
# Price Rules & Discounts
# ─────────────────────────────────────────────

@router.get("/price_rules", summary="List price rules")
def list_price_rules(limit: int = Query(50)):
    try:
        return sh.list_price_rules(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/price_rules", summary="Create a price rule")
def create_price_rule(req: CreatePriceRuleRequest):
    try:
        return sh.create_price_rule(
            title=req.title,
            value_type=req.value_type,
            value=req.value,
            customer_selection=req.customer_selection,
            target_type=req.target_type,
            target_selection=req.target_selection,
            allocation_method=req.allocation_method,
            starts_at=req.starts_at,
            ends_at=req.ends_at,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/price_rules/{price_rule_id}/discount_codes",
            summary="List discount codes for a price rule")
def list_discount_codes(price_rule_id: int):
    try:
        return sh.list_discount_codes(price_rule_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/price_rules/{price_rule_id}/discount_codes",
             summary="Create a discount code")
def create_discount_code(price_rule_id: int, req: CreateDiscountCodeRequest):
    try:
        return sh.create_discount_code(price_rule_id, req.code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─────────────────────────────────────────────
# Collections
# ─────────────────────────────────────────────

@router.get("/collections/custom", summary="List custom collections")
def list_custom_collections(limit: int = Query(50)):
    try:
        return sh.list_custom_collections(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/collections/smart", summary="List smart collections")
def list_smart_collections(limit: int = Query(50)):
    try:
        return sh.list_smart_collections(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─────────────────────────────────────────────
# Metafields
# ─────────────────────────────────────────────

@router.get("/metafields", summary="List metafields for a resource")
def list_metafields(
    owner_resource: str = Query(..., description="product, page, collection, article, shop"),
    owner_id: int = Query(...),
):
    try:
        return sh.list_metafields(owner_resource, owner_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/metafields", summary="Create/update a metafield")
def set_metafield(req: SetMetafieldRequest):
    try:
        return sh.set_metafield(
            req.owner_resource, req.owner_id,
            req.namespace, req.key, req.value, req.type_
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
