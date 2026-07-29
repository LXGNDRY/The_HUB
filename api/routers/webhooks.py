"""
Shopify Webhook Receiver — /webhooks
=====================================
Receives real-time event payloads from Shopify and dispatches them to
automation handlers. All requests are HMAC-verified using SHOPIFY_WEBHOOK_SECRET.

Registered topics and their handlers:
  products/create  → on_product_created()
  products/update  → on_product_updated()  (only acts when status goes active)
  orders/paid      → on_order_paid()
  checkouts/create → on_checkout_created()

Route is mounted WITHOUT the X-API-Key guard (Shopify signs with HMAC instead).
Mount in api/main.py:
  app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
"""

import os
import hmac
import hashlib
import base64
import logging
import threading

from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional

logger = logging.getLogger("gcp-bot.webhooks")
router = APIRouter()

SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
SITE_DOMAIN = os.getenv("SITE_DOMAIN", "legendary-branding.com")


# ---------------------------------------------------------------------------
# HMAC verification
# ---------------------------------------------------------------------------

def _verify_hmac(body: bytes, hmac_header: str) -> bool:
    """
    Validate Shopify's X-Shopify-Hmac-Sha256 header.
    Returns True if the signature matches, False otherwise.
    """
    if not SHOPIFY_WEBHOOK_SECRET:
        logger.error("[webhooks] SHOPIFY_WEBHOOK_SECRET not configured — rejecting all webhooks.")
        return False
    digest = hmac.new(
        SHOPIFY_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, hmac_header)


# ---------------------------------------------------------------------------
# Async dispatch helpers
# ---------------------------------------------------------------------------

def _run_async(fn, *args, **kwargs):
    """Fire-and-forget in a daemon thread so the webhook returns 200 fast."""
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Product handlers
# ---------------------------------------------------------------------------

def _handle_product_created(payload: dict):
    """
    Called when a new Shopify product is created.
    Pipeline:
      1. Fill missing image alt text
      2. Submit product URL to Google Indexing API
      3. Ping IndexNow
    SEO meta rewrite is deferred to the nightly batch (seo_meta_rewrite.py).
    """
    product_id = payload.get("id")
    handle = payload.get("handle", "")
    title = payload.get("title", "")
    product_type = payload.get("product_type", "")
    tags = payload.get("tags", "")
    status = payload.get("status", "")

    logger.info("[webhooks] products/create — id=%s handle=%s status=%s", product_id, handle, status)

    if status not in ("active", ""):
        logger.info("[webhooks] product %s is %s — skipping onboarding pipeline.", product_id, status)
        return

    # 1. Fill missing alt text on images
    try:
        from modules.shopify import list_product_images, update_product_image_alt
        from config import DRY_RUN
        images = list_product_images(product_id)
        for idx, img in enumerate(images.get("images", []), start=1):
            if img.get("alt"):
                continue
            ptype_part = f" — {product_type}" if product_type else ""
            detail = f" Detail View {idx}" if idx > 1 else ""
            alt = f"{title}{ptype_part}{detail} | Legendary Branding"[:255]
            if not DRY_RUN:
                update_product_image_alt(product_id, img["id"], alt)
            logger.info("[webhooks] Set alt text on image %s for product %s", img["id"], product_id)
    except Exception as e:
        logger.error("[webhooks] Alt text fill failed for product %s: %s", product_id, e)

    if not handle:
        return

    product_url = f"https://{SITE_DOMAIN}/products/{handle}"

    # 2. Google Indexing API
    try:
        from modules.indexing import IndexingModule
        from auth.credentials import get_credentials
        mod = IndexingModule(get_credentials())
        mod.submit_url(product_url)
        logger.info("[webhooks] Submitted to Google Indexing API: %s", product_url)
    except Exception as e:
        logger.error("[webhooks] Google Indexing submission failed for %s: %s", product_url, e)

    # 3. IndexNow
    indexnow_key = os.getenv("INDEXNOW_API_KEY", "")
    if indexnow_key:
        try:
            import requests as _requests
            resp = _requests.post(
                "https://api.indexnow.org/indexnow",
                json={
                    "host": SITE_DOMAIN,
                    "key": indexnow_key,
                    "keyLocation": f"https://{SITE_DOMAIN}/pages/{indexnow_key}",
                    "urlList": [product_url],
                },
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("[webhooks] IndexNow pinged: %s", product_url)
        except Exception as e:
            logger.error("[webhooks] IndexNow ping failed for %s: %s", product_url, e)

    # 4. Set country of origin + HS code on all variants
    try:
        from modules.shopify import update_inventory_item_compliance
        from modules.product_compliance import infer_hs_code, resolve_coo
        tag_list = [t.strip() for t in (payload.get("tags") or "").split(",") if t.strip()]
        coo = resolve_coo(tag_list)
        hs_code = infer_hs_code(product_type, title)
        for variant in payload.get("variants", []):
            inv_id = variant.get("inventory_item_id")
            if not inv_id:
                continue
            inv_gid = f"gid://shopify/InventoryItem/{inv_id}"
            result = update_inventory_item_compliance(inv_gid, coo, hs_code)
            errs = result.get("data", {}).get("inventoryItemUpdate", {}).get("userErrors", [])
            if errs:
                logger.error("[webhooks] COO/HS update failed for %s: %s", inv_gid, errs)
            else:
                logger.info("[webhooks] Set COO=%s HS=%s on %s", coo, hs_code, inv_gid)
    except Exception as e:
        logger.error("[webhooks] COO/HS code assignment failed for product %s: %s", product_id, e)

    # 5. Ensure product_type is a canonical Google Shopping taxonomy string
    resolved_type = product_type
    try:
        from modules.shopify import update_product_type
        from modules.product_compliance import resolve_product_type
        resolved_type = resolve_product_type(product_type, title)
        if resolved_type != product_type:
            product_gid = f"gid://shopify/Product/{product_id}"
            result = update_product_type(product_gid, resolved_type)
            errs = result.get("data", {}).get("productUpdate", {}).get("userErrors", [])
            if errs:
                logger.error("[webhooks] product_type update failed for %s: %s", product_id, errs)
            else:
                logger.info("[webhooks] product_type '%s' → '%s' for product %s", product_type, resolved_type, product_id)
    except Exception as e:
        logger.error("[webhooks] product_type standardization failed for product %s: %s", product_id, e)

    # 6. Write google_product_category metafield so GMC receives the numeric taxonomy ID
    try:
        from modules.shopify import update_google_product_category
        from modules.product_compliance import resolve_gmc_category_id
        category_id = resolve_gmc_category_id(resolved_type)
        update_google_product_category(product_id, category_id)
        logger.info("[webhooks] google_product_category → %s for product %s", category_id, product_id)
    except Exception as e:
        logger.error("[webhooks] google_product_category write failed for product %s: %s", product_id, e)


def _handle_product_updated(payload: dict):
    """
    Called on products/update. Only runs the onboarding pipeline if the
    product just became active (draft → active transition).
    """
    status = payload.get("status", "")
    if status == "active":
        _handle_product_created(payload)


# ---------------------------------------------------------------------------
# Order handler
# ---------------------------------------------------------------------------

def _handle_order_paid(payload: dict):
    """
    Called when an order is paid. Fires a Klaviyo 'Placed Order' custom event
    to ensure abandoned cart and post-purchase flows trigger reliably,
    bridging any gap in the native Shopify→Klaviyo integration.
    """
    order_id = payload.get("id")
    email = payload.get("email", "")
    total_price = payload.get("total_price", "0.00")
    order_number = payload.get("order_number", "")
    line_items = payload.get("line_items", [])

    logger.info("[webhooks] orders/paid — order=%s email=%s total=%s", order_number, email, total_price)

    if not email:
        logger.warning("[webhooks] Order %s has no email — cannot fire Klaviyo event.", order_id)
        return

    try:
        from modules.klaviyo import KlaviyoModule
        klv = KlaviyoModule()
        klv.create_event(
            event_name="Placed Order",
            email=email,
            properties={
                "order_id": order_id,
                "order_number": order_number,
                "total_price": total_price,
                "item_count": len(line_items),
                "items": [
                    {
                        "title": item.get("title"),
                        "quantity": item.get("quantity"),
                        "price": item.get("price"),
                        "sku": item.get("sku"),
                    }
                    for item in line_items[:10]
                ],
            },
        )
        logger.info("[webhooks] Klaviyo 'Placed Order' event fired for %s", email)
    except Exception as e:
        logger.error("[webhooks] Klaviyo Placed Order event failed for order %s: %s", order_id, e)


# ---------------------------------------------------------------------------
# Checkout handler
# ---------------------------------------------------------------------------

def _handle_checkout_created(payload: dict):
    """
    Called when a checkout is created (potential abandoned cart).
    Fires a Klaviyo 'Started Checkout' event so the abandoned bag flow
    can trigger reliably without relying solely on native integration.
    """
    checkout_id = payload.get("id")
    email = payload.get("email", "")
    total_price = payload.get("total_price", "0.00")
    line_items = payload.get("line_items", [])

    logger.info("[webhooks] checkouts/create — id=%s email=%s", checkout_id, email)

    if not email:
        logger.debug("[webhooks] Checkout %s has no email yet — skipping Klaviyo event.", checkout_id)
        return

    try:
        from modules.klaviyo import KlaviyoModule
        klv = KlaviyoModule()
        klv.create_event(
            event_name="Started Checkout",
            email=email,
            properties={
                "checkout_id": checkout_id,
                "total_price": total_price,
                "item_count": len(line_items),
                "items": [
                    {
                        "title": item.get("title"),
                        "quantity": item.get("quantity"),
                        "price": item.get("price"),
                    }
                    for item in line_items[:10]
                ],
            },
        )
        logger.info("[webhooks] Klaviyo 'Started Checkout' event fired for %s", email)
    except Exception as e:
        logger.error("[webhooks] Klaviyo Started Checkout event failed for checkout %s: %s", checkout_id, e)


# ---------------------------------------------------------------------------
# Webhook routes
# ---------------------------------------------------------------------------

@router.post("/shopify", summary="Shopify webhook receiver (HMAC-verified)")
async def shopify_webhook(
    request: Request,
    x_shopify_topic: Optional[str] = Header(None),
    x_shopify_hmac_sha256: Optional[str] = Header(None),
):
    """
    Central Shopify webhook endpoint. Shopify sends all registered topics here.
    Verifies HMAC signature before processing any payload.
    Returns 200 immediately; processing happens in a background thread.
    """
    body = await request.body()

    # HMAC verification
    if not x_shopify_hmac_sha256:
        raise HTTPException(status_code=401, detail="Missing X-Shopify-Hmac-Sha256 header")
    if not _verify_hmac(body, x_shopify_hmac_sha256):
        logger.warning("[webhooks] HMAC verification failed for topic=%s", x_shopify_topic)
        raise HTTPException(status_code=401, detail="HMAC verification failed")

    import json
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    topic = x_shopify_topic or ""
    logger.info("[webhooks] Received topic=%s", topic)

    # Dispatch to handler in background thread
    if topic == "products/create":
        _run_async(_handle_product_created, payload)
    elif topic == "products/update":
        _run_async(_handle_product_updated, payload)
    elif topic == "orders/paid":
        _run_async(_handle_order_paid, payload)
    elif topic == "checkouts/create":
        _run_async(_handle_checkout_created, payload)
    else:
        logger.debug("[webhooks] Unhandled topic: %s — acknowledged", topic)

    return {"status": "received", "topic": topic}
