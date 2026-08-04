"""
Shopify Webhook Receiver — /webhooks
=====================================
Receives real-time event payloads from Shopify and dispatches them to
automation handlers. All requests are HMAC-verified using SHOPIFY_WEBHOOK_SECRET.

Registered topics and their handlers:
  products/create   → on_product_created()
  products/update   → on_product_updated()  (only acts when status goes active)
  orders/paid       → on_order_paid()
  orders/fulfilled  → on_order_fulfilled()  (shipping confirmation flow)
  checkouts/create  → on_checkout_event()   (fires Klaviyo if email present)
  checkouts/update  → on_checkout_event()   (fires Klaviyo when email captured)

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
# Checkout handler (shared by checkouts/create and checkouts/update)
# ---------------------------------------------------------------------------

def _handle_checkout_event(payload: dict, topic: str = "checkouts/create"):
    """
    Called when a checkout is created or updated.

    checkouts/create fires immediately on checkout start — email is absent for
    new customers at this point. checkouts/update fires when the customer fills
    in their email on the information step, which is when we first have a profile
    to enroll in the abandoned bag flow.

    Fires a Klaviyo 'Checkout Started' event (metric YdsnAF) whenever email is
    present. Klaviyo deduplicates rapid re-fires via the flow trigger window.
    """
    checkout_id = payload.get("id")
    email = payload.get("email", "")
    total_price = payload.get("total_price", "0.00")
    line_items = payload.get("line_items", [])

    logger.info("[webhooks] %s — id=%s email=%s", topic, checkout_id, email)

    if not email:
        logger.debug("[webhooks] Checkout %s has no email yet — skipping Klaviyo event.", checkout_id)
        return

    try:
        from modules.klaviyo import KlaviyoModule
        klv = KlaviyoModule()
        klv.create_event(
            event_name="Checkout Started",
            email=email,
            metric_id="YdsnAF",
            properties={
                "checkout_id": checkout_id,
                "checkout_url": payload.get("abandoned_checkout_url", ""),
                "total_price": total_price,
                "item_count": len(line_items),
                "line_items": [
                    {
                        "title": item.get("title"),
                        "variant_title": item.get("variant_title", ""),
                        "quantity": item.get("quantity"),
                        "price": item.get("price"),
                        "image_url": item.get("image_url", ""),
                    }
                    for item in line_items[:10]
                ],
            },
        )
        logger.info("[webhooks] Klaviyo 'Checkout Started' event fired for %s", email)
    except Exception as e:
        logger.error("[webhooks] Klaviyo Checkout Started event failed for checkout %s: %s", checkout_id, e)


# ---------------------------------------------------------------------------
# Order fulfilled handler
# ---------------------------------------------------------------------------

def _handle_order_fulfilled(payload: dict):
    """
    Called when an order is fulfilled. Fires a Klaviyo 'Fulfilled Order' event
    to trigger the Shipping Confirmation flow reliably, bridging any gap in the
    native Shopify→Klaviyo fulfillment integration.
    """
    order_id = payload.get("id")
    email = payload.get("email", "")
    order_number = payload.get("order_number", "")
    fulfillments = payload.get("fulfillments", [])

    tracking_number = ""
    tracking_url = ""
    if fulfillments:
        latest = fulfillments[-1]
        tracking_number = latest.get("tracking_number", "") or ""
        tracking_url = latest.get("tracking_url", "") or ""

    logger.info("[webhooks] orders/fulfilled — order=%s email=%s", order_number, email)

    if not email:
        logger.warning("[webhooks] Order %s fulfilled but has no email — skipping Klaviyo event.", order_id)
        return

    try:
        from modules.klaviyo import KlaviyoModule
        klv = KlaviyoModule()
        klv.create_event(
            event_name="Fulfilled Order",
            email=email,
            properties={
                "order_id": order_id,
                "order_number": order_number,
                "tracking_number": tracking_number,
                "tracking_url": tracking_url,
            },
        )
        logger.info("[webhooks] Klaviyo 'Fulfilled Order' event fired for %s", email)
    except Exception as e:
        logger.error("[webhooks] Klaviyo Fulfilled Order event failed for order %s: %s", order_id, e)


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
    elif topic == "orders/fulfilled":
        _run_async(_handle_order_fulfilled, payload)
    elif topic in ("checkouts/create", "checkouts/update"):
        _run_async(_handle_checkout_event, payload, topic)
    else:
        logger.debug("[webhooks] Unhandled topic: %s — acknowledged", topic)

    return {"status": "received", "topic": topic}
