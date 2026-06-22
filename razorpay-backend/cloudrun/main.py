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
  SHOPIFY_ADMIN_TOKEN    — shpat_...
  SHOPIFY_STORE_DOMAIN   — lngndny.myshopify.com
  WEBHOOK_SECRET         — Razorpay webhook secret (set in dashboard)
"""

import os
import hmac
import hashlib
import json
import logging
import requests

from flask import Flask, request, jsonify
from flask_cors import CORS

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
SHOPIFY_TOKEN   = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
SHOPIFY_DOMAIN  = os.environ.get("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
WEBHOOK_SECRET  = os.environ.get("WEBHOOK_SECRET", "")

RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"
SHOPIFY_GRAPHQL_URL = f"https://{SHOPIFY_DOMAIN}/admin/api/2025-01/graphql.json"

# Exchange rate fallback — if live fetch fails, use this floor
# Update this periodically or wire in a live FX API post-launch
USD_TO_INR_FALLBACK = 84.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_usd_to_inr() -> float:
    """Fetch live USD→INR rate. Falls back to USD_TO_INR_FALLBACK on error."""
    try:
        resp = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=3
        )
        data = resp.json()
        return float(data["rates"]["INR"])
    except Exception as e:
        log.warning(f"FX fetch failed, using fallback rate: {e}")
        return USD_TO_INR_FALLBACK


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
        "X-Shopify-Access-Token": SHOPIFY_TOKEN
    }
    resp = requests.post(
        SHOPIFY_GRAPHQL_URL,
        headers=headers,
        json={"query": query, "variables": variables},
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()


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


# ---------------------------------------------------------------------------
# Route: POST /health
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "lb-razorpay-backend"}), 200


# ---------------------------------------------------------------------------
# Route: POST /create-order
# ---------------------------------------------------------------------------
@app.route("/create-order", methods=["POST"])
def create_order():
    """
    Creates a Razorpay order.

    Request body (JSON):
      amount        int    — cart total in subunits (Shopify cents, e.g. 6400 for $64)
      currency      str    — cart currency ISO code (e.g. 'USD') — used for INR conversion
      customer_email str   — prefill
      customer_name  str   — prefill

    Returns:
      id            str    — Razorpay order_id  (MUST pass to frontend checkout options)
      amount        int    — amount in paise
      currency      str    — always 'INR'
      amount_display str   — human-readable for logging
    """
    data = request.get_json(force=True, silent=True) or {}

    # Amount arrives in subunits (Shopify: cents). Convert to INR paise.
    cart_amount_subunits = int(data.get("amount", 0))
    cart_currency = str(data.get("currency", "USD")).upper()

    if cart_amount_subunits <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    # Convert to base units first (divide by 100)
    cart_amount_base = cart_amount_subunits / 100.0

    # Always settle in INR — Razorpay Import Flow settles in INR regardless
    if cart_currency == "INR":
        amount_inr_paise = cart_amount_subunits  # already paise
    else:
        # Convert USD (or other) → INR, then to paise
        fx_rate = get_usd_to_inr()
        amount_inr = cart_amount_base * fx_rate
        amount_inr_paise = int(round(amount_inr * 100))

    if amount_inr_paise < 100:  # Razorpay minimum: ₹1
        return jsonify({"error": "Amount below minimum"}), 400

    # Build Razorpay order payload
    receipt = f"lb_{os.urandom(4).hex()}"
    payload = {
        "amount": amount_inr_paise,
        "currency": "INR",
        "receipt": receipt,
        "notes": {
            "customer_email": data.get("customer_email", ""),
            "customer_name": data.get("customer_name", ""),
            "cart_currency": cart_currency,
            "cart_amount_usd": str(cart_amount_base)
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
        "amount_display": f"₹{amount_inr_paise/100:.2f}"
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

    # --- Step 2: Build Shopify Draft Order ---
    cart_items = data.get("cart_items", [])
    customer_email = data.get("customer_email", "")
    customer_name  = data.get("customer_name", "")
    shipping_addr  = data.get("shipping_address", {})

    # Parse name into first/last
    name_parts = customer_name.strip().split(" ", 1)
    first_name = name_parts[0] if name_parts else ""
    last_name  = name_parts[1] if len(name_parts) > 1 else ""

    # Line items — Shopify expects variantId as GID
    line_items = []
    for item in cart_items:
        variant_id = item.get("variant_id", "")
        # Accept both numeric and GID format
        if not str(variant_id).startswith("gid://"):
            variant_id = f"gid://shopify/ProductVariant/{variant_id}"
        line_items.append({
            "variantId": variant_id,
            "quantity": int(item.get("quantity", 1))
        })

    draft_input = {
        "email": customer_email,
        "lineItems": line_items,
        "shippingAddress": {
            "firstName":  shipping_addr.get("first_name", first_name),
            "lastName":   shipping_addr.get("last_name", last_name),
            "address1":   shipping_addr.get("address1", ""),
            "city":       shipping_addr.get("city", ""),
            "country":    shipping_addr.get("country", "IN"),
            "zip":        shipping_addr.get("zip", ""),
            "phone":      shipping_addr.get("phone", "")
        },
        "billingAddress": {
            "firstName":  shipping_addr.get("first_name", first_name),
            "lastName":   shipping_addr.get("last_name", last_name),
            "address1":   shipping_addr.get("address1", ""),
            "city":       shipping_addr.get("city", ""),
            "country":    shipping_addr.get("country", "IN"),
            "zip":        shipping_addr.get("zip", ""),
        },
        "note": f"Razorpay | order_id={order_id} | payment_id={payment_id}",
        "tags": "razorpay,upi,india",
        "customAttributes": [
            {"key": "razorpay_order_id",   "value": order_id},
            {"key": "razorpay_payment_id", "value": payment_id}
        ]
    }

    try:
        # Step 2a: Create draft order
        result = shopify_graphql(DRAFT_ORDER_CREATE, {"input": draft_input})
        errors = result.get("data", {}).get("draftOrderCreate", {}).get("userErrors", [])
        if errors:
            log.error(f"Shopify draft order errors: {errors}")
            return jsonify({"error": "Shopify order creation failed", "details": errors}), 502

        draft = result["data"]["draftOrderCreate"]["draftOrder"]
        draft_id = draft["id"]
        log.info(f"Draft order created: {draft_id}")

        # Step 2b: Complete draft order (mark as paid — payment already captured by Razorpay)
        complete_result = shopify_graphql(
            DRAFT_ORDER_COMPLETE,
            {"id": draft_id, "paymentPending": False}
        )
        complete_errors = complete_result.get("data", {}).get("draftOrderComplete", {}).get("userErrors", [])
        if complete_errors:
            log.error(f"Shopify draft complete errors: {complete_errors}")
            return jsonify({"error": "Shopify order completion failed", "details": complete_errors}), 502

        order = complete_result["data"]["draftOrderComplete"]["draftOrder"]["order"]
        log.info(f"Shopify order created: {order['name']} | {order['id']}")

    except Exception as e:
        log.error(f"Shopify order creation exception: {e}")
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

    # Verify webhook authenticity
    if WEBHOOK_SECRET and not verify_webhook_signature(payload_bytes, received_sig):
        log.warning("Webhook signature verification failed")
        return jsonify({"error": "Invalid signature"}), 400

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
        # Future: trigger SFTP invoice upload Cloud Function here

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
