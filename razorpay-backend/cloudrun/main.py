"""
Legendary Branding — Razorpay Cloud Run Backend
================================================
Endpoints:
  POST /create-order     — Creates a Razorpay order (INR), returns order_id
  POST /verify-payment   — Verifies HMAC signature, creates Shopify Draft Order
  POST /webhook          — Handles payment.captured / payment.failed events

Environment (via GCP Secret Manager):
  RAZORPAY_KEY_ID        — rzp_live_...
  RAZORPAY_KEY_SECRET    — live secret
  SHOPIFY_CLIENT_ID      — Shopify custom app API key
  SHOPIFY_CLIENT_SECRET  — Shopify custom app API secret (shpss_...)
  SHOPIFY_STORE_DOMAIN   — lngndny.myshopify.com
  WEBHOOK_SECRET         — Razorpay webhook secret (set in dashboard)

Shopify auth uses OAuth Client Credentials Grant (same pattern as gcp-bot's
modules/shopify.py) — SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET are exchanged
for a short-lived Admin API access token, cached in memory and refreshed
before expiry. No static SHOPIFY_ADMIN_TOKEN is required.
"""

import os
import time
import hmac
import hashlib
import json
import logging
import requests
import threading

from flask import Flask, request, jsonify
from flask_cors import CORS

# SFTP invoice uploader — runs in background thread on payment.captured
try:
    from sftp.sftp_upload import upload_invoice
    SFTP_ENABLED = True
except ImportError:
    SFTP_ENABLED = False
    logging.getLogger(__name__).warning("sftp_upload module not found — SFTP uploads disabled")

app = Flask(__name__)

# Allow requests from the Legendary Branding storefront only
CORS(app, origins=[
    "https://legendary-branding.com",
    "https://lngndny.myshopify.com"
])

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — pulled from environment (Secret Manager injects at runtime)
# ---------------------------------------------------------------------------
RZP_KEY_ID      = os.environ.get("RAZORPAY_KEY_ID", "")
RZP_KEY_SECRET  = os.environ.get("RAZORPAY_KEY_SECRET", "")
SHOPIFY_CLIENT_ID     = os.environ.get("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOPIFY_DOMAIN  = os.environ.get("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
WEBHOOK_SECRET  = os.environ.get("WEBHOOK_SECRET", "")

RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"
SHOPIFY_GRAPHQL_URL = f"https://{SHOPIFY_DOMAIN}/admin/api/2026-04/graphql.json"
SHOPIFY_OAUTH_URL   = f"https://{SHOPIFY_DOMAIN}/admin/oauth/access_token"

# How many seconds before expiry to proactively refresh
SHOPIFY_TOKEN_REFRESH_BUFFER = 300  # 5 minutes


class _ShopifyTokenCache:
    """Thread-safe in-memory Admin API token, refreshed via OAuth Client
    Credentials Grant (SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET) before
    expiry — mirrors modules/shopify.py's _TokenCache in the main gcp-bot."""

    def __init__(self):
        self._lock = threading.Lock()
        self._token = ""
        self._expires_at = 0.0

    def get(self) -> str:
        with self._lock:
            if time.time() >= (self._expires_at - SHOPIFY_TOKEN_REFRESH_BUFFER):
                self._refresh()
            return self._token

    def _refresh(self):
        if not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
            raise RuntimeError(
                "SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET must be set to obtain a Shopify admin token."
            )
        log.info("Shopify token near expiry — requesting new Client Credentials token...")
        r = requests.post(
            SHOPIFY_OAUTH_URL,
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
        log.info(f"Shopify token refreshed, expires in {expires_in}s")


_shopify_token_cache = _ShopifyTokenCache()

# Exchange rate — cached for 5 minutes to avoid hammering open.er-api.com
USD_TO_INR_FALLBACK = 84.0
_FX_CACHE_TTL = 300
_fx_cache: dict = {"rate": USD_TO_INR_FALLBACK, "ts": 0.0}

# Idempotency guard — prevents duplicate Shopify orders on retries.
# In-memory set; does not survive restarts or span multiple instances, but
# it protects against same-instance double-calls (e.g. double-click, retries).
_processed_payment_ids: set = set()
_payment_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_usd_to_inr() -> float:
    """Fetch live USD→INR rate, cached for 5 minutes. Falls back on error."""
    now = time.time()
    if now - _fx_cache["ts"] < _FX_CACHE_TTL:
        return _fx_cache["rate"]
    try:
        resp = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=3
        )
        data = resp.json()
        rate = float(data["rates"]["INR"])
        _fx_cache["rate"] = rate
        _fx_cache["ts"] = now
        return rate
    except Exception as e:
        log.warning(f"FX fetch failed, using cached/fallback rate: {e}")
        return _fx_cache["rate"]


def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Verify HMAC SHA256 signature per Razorpay docs:
      generated = hmac_sha256(order_id + "|" + payment_id, key_secret)
    """
    body = f"{order_id}|{payment_id}"
    generated = hmac.new(
        RZP_KEY_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(generated, signature)


def verify_webhook_signature(payload_bytes: bytes, received_sig: str) -> bool:
    """Verify Razorpay webhook signature using WEBHOOK_SECRET."""
    generated = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(generated, received_sig)


def shopify_graphql(query: str, variables: dict) -> dict:
    """Execute a Shopify Admin GraphQL request."""
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": _shopify_token_cache.get()
    }
    resp = requests.post(
        SHOPIFY_GRAPHQL_URL,
        headers=headers,
        json={"query": query, "variables": variables},
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()


def _try_claim_payment(payment_id: str) -> bool:
    """Thread-safe idempotency check. Returns True if this caller claimed the
    payment_id (i.e. first to process it). Returns False if already processed."""
    with _payment_lock:
        if payment_id in _processed_payment_ids:
            return False
        _processed_payment_ids.add(payment_id)
        return True


# ---------------------------------------------------------------------------
# GraphQL mutations
# ---------------------------------------------------------------------------

DRAFT_ORDER_CREATE = """
mutation draftOrderCreate($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    draftOrder {
      id
      name
      totalPrice
      invoiceUrl
    }
    userErrors {
      field
      message
    }
  }
}
"""

DRAFT_ORDER_COMPLETE = """
mutation draftOrderComplete($id: ID!, $paymentPending: Boolean) {
  draftOrderComplete(id: $id, paymentPending: $paymentPending) {
    draftOrder {
      id
      order {
        id
        name
        statusUrl
        confirmationNumber
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""

DRAFT_ORDER_CALCULATE = """
mutation draftOrderCalculate($input: DraftOrderInput!) {
  draftOrderCalculate(input: $input) {
    calculatedDraftOrder {
      subtotalPrice
      totalTax
      totalPrice
      availableShippingRates {
        handle
        title
        price {
          amount
          currencyCode
        }
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


def _create_shopify_order(
    payment_id: str,
    order_id: str,
    cart_items: list,
    customer_email: str,
    customer_name: str,
    shipping_addr: dict,
    shipping_line: dict = None
) -> dict:
    """Create and complete a Shopify Draft Order for a captured Razorpay payment.

    Returns the Shopify order dict with keys: id, name, statusUrl, confirmationNumber.
    Raises on any failure.
    """
    name_parts = customer_name.strip().split(" ", 1)
    first_name = name_parts[0] if name_parts else ""
    last_name  = name_parts[1] if len(name_parts) > 1 else ""

    line_items = []
    for item in cart_items:
        variant_id = item.get("variant_id", "")
        if not str(variant_id).startswith("gid://"):
            variant_id = f"gid://shopify/ProductVariant/{variant_id}"
        line_items.append({
            "variantId": variant_id,
            "quantity": int(item.get("quantity", 1))
        })

    # shipping_address is optional — Razorpay collects contact info in its modal.
    # If absent, we still create the order; merchant follows up for shipping details.
    addr_first   = shipping_addr.get("first_name", first_name)
    addr_last    = shipping_addr.get("last_name", last_name)
    addr_address = shipping_addr.get("address1", "Pending — collected via Razorpay")
    addr_city    = shipping_addr.get("city", "Pending")
    addr_country = shipping_addr.get("country", "IN")
    addr_zip     = shipping_addr.get("zip", "000000")
    addr_phone   = shipping_addr.get("phone", "")

    has_address = bool(shipping_addr.get("address1"))
    note_suffix = "" if has_address else " | Shipping address: to be confirmed with customer"

    draft_input = {
        "email": customer_email,
        "lineItems": line_items,
        "shippingAddress": {
            "firstName": addr_first,
            "lastName":  addr_last,
            "address1":  addr_address,
            "city":      addr_city,
            "country":   addr_country,
            "zip":       addr_zip,
            "phone":     addr_phone,
        },
        "billingAddress": {
            "firstName": addr_first,
            "lastName":  addr_last,
            "address1":  addr_address,
            "city":      addr_city,
            "country":   addr_country,
            "zip":       addr_zip,
        },
        "note": f"Razorpay | order_id={order_id} | payment_id={payment_id}{note_suffix}",
        "tags": "razorpay,upi,india",
        "customAttributes": [
            {"key": "razorpay_order_id",   "value": order_id},
            {"key": "razorpay_payment_id", "value": payment_id}
        ]
    }

    # Attach shipping line calculated at order-creation time so the Shopify
    # order reflects the correct shipping charge the customer was shown.
    if shipping_line and shipping_line.get("title"):
        draft_input["shippingLine"] = {
            "title": shipping_line["title"],
            "price": str(shipping_line.get("price", "0.00"))
        }

    result = shopify_graphql(DRAFT_ORDER_CREATE, {"input": draft_input})
    errors = result.get("data", {}).get("draftOrderCreate", {}).get("userErrors", [])
    if errors:
        raise RuntimeError(f"Shopify draft order errors: {errors}")

    draft = result["data"]["draftOrderCreate"]["draftOrder"]
    draft_id = draft["id"]
    log.info(f"Draft order created: {draft_id}")

    complete_result = shopify_graphql(
        DRAFT_ORDER_COMPLETE,
        {"id": draft_id, "paymentPending": False}
    )
    complete_errors = complete_result.get("data", {}).get("draftOrderComplete", {}).get("userErrors", [])
    if complete_errors:
        raise RuntimeError(f"Shopify draft complete errors: {complete_errors}")

    order = complete_result["data"]["draftOrderComplete"]["draftOrder"]["order"]
    log.info(f"Shopify order created: {order['name']} | {order['id']}")
    return order


def _get_shopify_calculated_total(cart_items: list, customer_email: str = "") -> dict:
    """
    Call draftOrderCalculate with a placeholder India address to get Shopify's
    tax-inclusive total. Returns a breakdown dict, or None on failure.

    The placeholder India address (Mumbai, Maharashtra) gives accurate GST
    estimates — GST rates are uniform across India; only CGST/SGST vs IGST
    split differs by state, not the total rate.
    """
    line_items = []
    for item in cart_items:
        variant_id = item.get("variant_id", "")
        if not str(variant_id).startswith("gid://"):
            variant_id = f"gid://shopify/ProductVariant/{variant_id}"
        line_items.append({
            "variantId": variant_id,
            "quantity": int(item.get("quantity", 1))
        })

    if not line_items:
        return None

    draft_input = {
        "lineItems": line_items,
        "shippingAddress": {
            "firstName": "India",
            "lastName": "Customer",
            "address1": "123 MG Road",
            "city": "Mumbai",
            "province": "Maharashtra",
            "country": "IN",
            "zip": "400001"
        }
    }
    if customer_email:
        draft_input["email"] = customer_email

    try:
        result = shopify_graphql(DRAFT_ORDER_CALCULATE, {"input": draft_input})
        calc_data = result.get("data", {}).get("draftOrderCalculate", {})
        errors = calc_data.get("userErrors", [])
        if errors:
            log.warning(f"draftOrderCalculate userErrors: {errors}")
            return None

        co = calc_data.get("calculatedDraftOrder") or {}

        subtotal = float(co.get("subtotalPrice") or 0)
        tax      = float(co.get("totalTax") or 0)

        # Pick cheapest available shipping rate (free if available)
        rates = co.get("availableShippingRates") or []
        shipping_price  = 0.0
        shipping_title  = "Free Shipping"
        shipping_handle = None
        if rates:
            def _rate_price(r):
                try:
                    return float((r.get("price") or {}).get("amount", 0))
                except Exception:
                    return 999.0
            best = min(rates, key=_rate_price)
            shipping_price  = float((best.get("price") or {}).get("amount", 0))
            shipping_title  = best.get("title") or "Standard Shipping"
            shipping_handle = best.get("handle")

        total = subtotal + tax + shipping_price

        log.info(
            f"draftOrderCalculate: subtotal=${subtotal:.2f} tax=${tax:.2f} "
            f"shipping=${shipping_price:.2f} ({shipping_title}) total=${total:.2f}"
        )

        return {
            "subtotal_usd":      subtotal,
            "tax_usd":           tax,
            "shipping_usd":      shipping_price,
            "total_usd":         total,
            "shipping_title":    shipping_title,
            "shipping_price_usd": shipping_price,
            "shipping_handle":   shipping_handle,
        }

    except Exception as e:
        log.error(f"draftOrderCalculate failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Route: GET /health
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "lb-razorpay-backend"}), 200


# ---------------------------------------------------------------------------
# Route: GET /.well-known/apple-developer-merchantid-domain-association
# Serves Apple Pay domain verification file for Razorpay
# ---------------------------------------------------------------------------
@app.route("/.well-known/apple-developer-merchantid-domain-association", methods=["GET"])
def apple_pay_domain_association():
    content = '{"version":1,"pspId":"1EDBF0FDBF5FA2065E29979C27D7CC7C95341B4E065BD8D8831658022009A572","createdOn":1749646752541}'
    from flask import Response
    return Response(
        content,
        status=200,
        mimetype="text/plain",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Access-Control-Allow-Origin": "*",
        }
    )


# ---------------------------------------------------------------------------
# Route: POST /create-order
# ---------------------------------------------------------------------------
@app.route("/create-order", methods=["POST"])
def create_order():
    """
    Creates a Razorpay order.

    Request body (JSON):
      amount              int    — cart total in subunits (Shopify cents, e.g. 6400 for $64)
      currency            str    — cart currency ISO code (e.g. 'USD') — used for INR conversion
      customer_email      str    — prefill
      customer_name       str    — prefill
      cart_items          list   — [{variant_id, quantity, price}] stored in notes for webhook fallback
      shipping_address    dict   — {first_name, last_name, address1, city, zip, country, phone}

    Returns:
      id            str    — Razorpay order_id  (MUST pass to frontend checkout options)
      amount        int    — amount in paise
      currency      str    — always 'INR'
      amount_display str   — human-readable for logging
    """
    data = request.get_json(force=True, silent=True) or {}

    # Amount arrives in subunits (Shopify: cents). Used as fallback only.
    cart_amount_subunits = int(data.get("amount", 0))
    cart_currency = str(data.get("currency", "USD")).upper()

    if cart_amount_subunits <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    customer_email = data.get("customer_email", "")
    customer_name  = data.get("customer_name", "")
    cart_items     = data.get("cart_items", [])

    # --- Ask Shopify for the tax-inclusive total ---
    # draftOrderCalculate returns subtotal + GST + shipping, ensuring the
    # customer is charged the correct amount (not just the cart subtotal).
    shopify_calc   = _get_shopify_calculated_total(cart_items, customer_email) if cart_items else None
    shipping_line  = None

    if shopify_calc:
        cart_amount_base = shopify_calc["total_usd"]
        cart_currency    = "USD"
        shipping_line    = {
            "title": shopify_calc["shipping_title"],
            "price": f"{shopify_calc['shipping_price_usd']:.2f}"
        }
        log.info(
            f"Using Shopify-calculated total: ${cart_amount_base:.2f} "
            f"(subtotal ${shopify_calc['subtotal_usd']:.2f} + "
            f"tax ${shopify_calc['tax_usd']:.2f} + "
            f"shipping ${shopify_calc['shipping_usd']:.2f})"
        )
    else:
        # Fallback: use cart subtotal provided by frontend
        log.warning("draftOrderCalculate unavailable — falling back to frontend-provided subtotal (taxes/shipping excluded)")
        cart_amount_base = cart_amount_subunits / 100.0

    # Always settle in INR — Razorpay Import Flow settles in INR regardless
    if cart_currency == "INR":
        amount_inr_paise = int(round(cart_amount_base * 100))
    else:
        fx_rate = get_usd_to_inr()
        amount_inr = cart_amount_base * fx_rate
        amount_inr_paise = int(round(amount_inr * 100))

    if amount_inr_paise < 100:  # Razorpay minimum: ₹1
        return jsonify({"error": "Amount below minimum"}), 400

    # Serialize cart items and shipping address into notes for webhook fallback.
    # Razorpay notes: up to 15 keys, values capped at 512 chars each.
    cart_items_json    = json.dumps(cart_items, separators=(",", ":"))
    shipping_addr_json = json.dumps(data.get("shipping_address", {}), separators=(",", ":"))
    shipping_line_json = json.dumps(shipping_line, separators=(",", ":")) if shipping_line else ""

    if len(cart_items_json) > 512:
        log.warning(f"cart_items_json too large ({len(cart_items_json)} chars) — webhook fallback may not reconstruct order")
        cart_items_json = cart_items_json[:512]
    if len(shipping_addr_json) > 512:
        shipping_addr_json = shipping_addr_json[:512]

    receipt = f"lb_{os.urandom(4).hex()}"
    payload = {
        "amount": amount_inr_paise,
        "currency": "INR",
        "receipt": receipt,
        "notes": {
            "customer_email":        customer_email,
            "customer_name":         customer_name,
            "cart_currency":         cart_currency,
            "cart_amount_usd":       str(cart_amount_base),
            "cart_items_json":       cart_items_json,
            "shipping_address_json": shipping_addr_json,
            "shipping_line_json":    shipping_line_json,
        }
    }

    try:
        resp = requests.post(
            RAZORPAY_ORDERS_URL,
            json=payload,
            auth=(RZP_KEY_ID, RZP_KEY_SECRET),
            timeout=10
        )
        resp.raise_for_status()
        order = resp.json()
    except requests.exceptions.HTTPError as e:
        log.error(f"Razorpay order creation failed: {e.response.text}")
        return jsonify({"error": "Razorpay order creation failed"}), 502
    except Exception as e:
        log.error(f"Unexpected error creating order: {e}")
        return jsonify({"error": "Internal server error"}), 500

    log.info(f"Order created: {order['id']} | ₹{amount_inr_paise/100:.2f} | receipt={receipt}")

    return jsonify({
        "id": order["id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "amount_display": f"₹{amount_inr_paise/100:.2f}",
        "shipping_line": shipping_line  # forwarded to /verify-payment by frontend
    }), 200


# ---------------------------------------------------------------------------
# Route: POST /verify-payment
# ---------------------------------------------------------------------------
@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    """
    Verifies Razorpay HMAC signature and creates a Shopify order.

    Request body (JSON):
      razorpay_payment_id   str
      razorpay_order_id     str
      razorpay_signature    str
      cart_items            list  — Shopify line items [{variant_id, quantity, price}]
      customer_email        str
      customer_name         str
      shipping_address      dict  — {first_name, last_name, address1, city, country, zip}

    Returns:
      success               bool
      shopify_order_id      str
      order_name            str   — e.g. #1042
      order_status_url      str   — redirect target
    """
    data = request.get_json(force=True, silent=True) or {}

    payment_id = data.get("razorpay_payment_id", "")
    order_id   = data.get("razorpay_order_id", "")
    signature  = data.get("razorpay_signature", "")

    # --- Step 1: Verify signature (mandatory — skip = fraud vector) ---
    if not all([payment_id, order_id, signature]):
        return jsonify({"error": "Missing payment verification fields"}), 400

    if not verify_razorpay_signature(order_id, payment_id, signature):
        log.warning(f"Signature mismatch for order {order_id} payment {payment_id}")
        return jsonify({"error": "Payment verification failed"}), 400

    log.info(f"Signature verified: order={order_id} payment={payment_id}")

    # --- Idempotency check ---
    if not _try_claim_payment(payment_id):
        log.warning(f"Duplicate verify-payment call for payment_id={payment_id}, skipping")
        return jsonify({"error": "Payment already processed"}), 409

    # --- Step 2: Create Shopify order ---
    try:
        order = _create_shopify_order(
            payment_id=payment_id,
            order_id=order_id,
            cart_items=data.get("cart_items", []),
            customer_email=data.get("customer_email", ""),
            customer_name=data.get("customer_name", ""),
            shipping_addr=data.get("shipping_address", {}),
            shipping_line=data.get("shipping_line")
        )
    except Exception as e:
        log.error(f"Shopify order creation exception: {e}")
        # Release the claim so webhook fallback can retry
        with _payment_lock:
            _processed_payment_ids.discard(payment_id)
        return jsonify({"error": "Shopify order creation failed"}), 500

    return jsonify({
        "success": True,
        "shopify_order_id": order["id"],
        "order_name": order["name"],
        "order_status_url": order.get("statusUrl", "/pages/order-confirmed"),
        "confirmation_number": order.get("confirmationNumber", "")
    }), 200


# ---------------------------------------------------------------------------
# Route: POST /webhook
# ---------------------------------------------------------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Handles Razorpay webhook events.
    Subscribed events: payment.captured, payment.failed, order.paid

    Razorpay signs webhooks with X-Razorpay-Signature header using WEBHOOK_SECRET.
    """
    payload_bytes = request.get_data()
    received_sig  = request.headers.get("X-Razorpay-Signature", "")

    # Verify webhook authenticity — WEBHOOK_SECRET must be set in production
    if WEBHOOK_SECRET:
        if not verify_webhook_signature(payload_bytes, received_sig):
            log.warning("Webhook signature verification failed")
            return jsonify({"error": "Invalid signature"}), 400
    else:
        log.warning("WEBHOOK_SECRET not set — skipping signature verification (insecure)")

    try:
        event = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON"}), 400

    event_type = event.get("event", "")
    payload    = event.get("payload", {})

    log.info(f"Webhook received: {event_type}")

    if event_type == "payment.captured":
        payment = payload.get("payment", {}).get("entity", {})
        payment_id = payment.get("id")
        order_id   = payment.get("order_id")
        amount     = payment.get("amount", 0)
        log.info(f"Payment captured: {payment_id} | order={order_id} | ₹{amount/100:.2f}")

        # Fallback order creation: if /verify-payment never fired (browser crash,
        # network drop), create the Shopify order here using cart data stored in
        # the Razorpay order notes at /create-order time.
        if payment_id and _try_claim_payment(payment_id):
            def _webhook_order_fallback():
                try:
                    rzp_resp = requests.get(
                        f"{RAZORPAY_ORDERS_URL}/{order_id}",
                        auth=(RZP_KEY_ID, RZP_KEY_SECRET),
                        timeout=10
                    )
                    rzp_resp.raise_for_status()
                    notes = rzp_resp.json().get("notes", {})

                    cart_items_raw     = notes.get("cart_items_json", "")
                    shipping_addr_raw  = notes.get("shipping_address_json", "")
                    shipping_line_raw  = notes.get("shipping_line_json", "")

                    if not cart_items_raw:
                        log.warning(f"Webhook fallback: missing cart_items in notes for order {order_id} — cannot create Shopify order")
                        return

                    cart_items    = json.loads(cart_items_raw)
                    shipping_addr = json.loads(shipping_addr_raw) if shipping_addr_raw else {}
                    shipping_line = json.loads(shipping_line_raw) if shipping_line_raw else None

                    _create_shopify_order(
                        payment_id=payment_id,
                        order_id=order_id,
                        cart_items=cart_items,
                        customer_email=notes.get("customer_email", ""),
                        customer_name=notes.get("customer_name", ""),
                        shipping_addr=shipping_addr,
                        shipping_line=shipping_line
                    )
                    log.info(f"Webhook fallback: Shopify order created for payment {payment_id}")
                except Exception as err:
                    log.error(f"Webhook fallback order creation failed for {payment_id}: {err}")
                    with _payment_lock:
                        _processed_payment_ids.discard(payment_id)

            threading.Thread(target=_webhook_order_fallback, daemon=True).start()
        else:
            log.info(f"Webhook: payment {payment_id} already handled by /verify-payment — skipping fallback")

        # SFTP invoice upload (non-blocking)
        if SFTP_ENABLED:
            invoice_payload = [{
                "payment_id":         payment_id,
                "order_id":           order_id,
                "amount_paise":       int(amount),
                "currency":           payment.get("currency", "INR"),
                "status":             "captured",
                "method":             payment.get("method", ""),
                "email":              payment.get("email", ""),
                "contact":            payment.get("contact", ""),
                "description":        payment.get("description", "Legendary Branding"),
                "created_at":         payment.get("created_at", 0),
                "merchant_order_id":  payment.get("notes", {}).get("merchant_order_id", ""),
                "shopify_order_name": payment.get("notes", {}).get("shopify_order_name", ""),
            }]
            def _sftp_upload():
                try:
                    filename = upload_invoice(invoice_payload)
                    log.info(f"SFTP invoice uploaded: {filename}")
                except Exception as sftp_err:
                    log.error(f"SFTP upload error (non-fatal): {sftp_err}")
            threading.Thread(target=_sftp_upload, daemon=True).start()

    elif event_type == "payment.failed":
        payment = payload.get("payment", {}).get("entity", {})
        payment_id = payment.get("id")
        error_desc = payment.get("error_description", "unknown")
        log.warning(f"Payment failed: {payment_id} | reason={error_desc}")
        # Future: fire Klaviyo abandoned checkout flow

    elif event_type == "order.paid":
        order = payload.get("order", {}).get("entity", {})
        order_id = order.get("id")
        log.info(f"Order paid: {order_id}")

    # Always return 200 — Razorpay retries on non-200
    return jsonify({"status": "received"}), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
