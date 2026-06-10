#!/usr/bin/env python3
"""
Enhanced Conversions — Server-Side Reporter
Sends hashed customer data from Shopify orders to Google Ads API
as enhanced conversion hits tied to the purchase conversion action.

Usage:
  python scripts/gmc_enhanced_conversions.py --list-actions
  python scripts/gmc_enhanced_conversions.py --order <ORDER_ID>
  python scripts/gmc_enhanced_conversions.py --backfill  (processes recent paid orders)
"""

import os
import sys
import json
import hashlib
import argparse
import time
from datetime import datetime, timezone, timedelta

import requests
from google.oauth2 import service_account
import google.auth.transport.requests

# ── Config ─────────────────────────────────────────────────────────────────
CUSTOMER_ID      = "1137623123"
SHOPIFY_STORE    = "lngndny.myshopify.com"
SHOPIFY_TOKEN    = os.environ["SHOPIFY_ADMIN_TOKEN"]
GCP_SA_KEY_JSON  = os.environ["GCP_SA_KEY"]

# Populated after --list-actions run; set here once confirmed
PURCHASE_CONVERSION_ACTION_ID = os.environ.get("CONVERSION_ACTION_ID", "")

SCOPES = ["https://www.googleapis.com/auth/adwords"]

# ── Auth ────────────────────────────────────────────────────────────────────
def get_ads_token():
    creds = service_account.Credentials.from_service_account_info(
        json.loads(GCP_SA_KEY_JSON), scopes=SCOPES
    )
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds.token


# ── Hashing ─────────────────────────────────────────────────────────────────
def sha256(value: str) -> str:
    """Normalize and SHA-256 hash a string per Google's spec."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


# ── Shopify helpers ──────────────────────────────────────────────────────────
def shopify_get(endpoint: str) -> dict:
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/{endpoint}"
    headers = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def get_order(order_id: str) -> dict:
    data = shopify_get(f"orders/{order_id}.json")
    return data["order"]


def get_recent_paid_orders(days: int = 3) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    data = shopify_get(f"orders.json?status=any&financial_status=paid&created_at_min={since}&limit=50")
    return data.get("orders", [])


# ── Google Ads helpers ───────────────────────────────────────────────────────
def list_conversion_actions(token: str) -> list:
    query = """
        SELECT
          conversion_action.id,
          conversion_action.name,
          conversion_action.type,
          conversion_action.status,
          conversion_action.category
        FROM conversion_action
        ORDER BY conversion_action.name ASC
    """
    url = f"https://googleads.googleapis.com/v17/customers/{CUSTOMER_ID}/googleAds:search"
    headers = {
        "Authorization": f"Bearer {token}",
        "developer-token": "",  # Not needed for SA auth via OAuth
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json={"query": query}, timeout=30)
    if not resp.ok:
        print(f"ERROR listing conversions: {resp.status_code} {resp.text[:500]}")
        return []
    results = resp.json().get("results", [])
    return results


def send_enhanced_conversion(token: str, order: dict, conversion_action_id: str) -> bool:
    """
    Send a single enhanced conversion hit for a Shopify order.
    Uses the UploadClickConversions endpoint with user identifiers.
    """
    customer  = order.get("customer", {})
    billing   = order.get("billing_address", {})
    email     = customer.get("email", "") or order.get("email", "")
    phone     = customer.get("phone", "") or billing.get("phone", "")
    first     = billing.get("first_name", "") or customer.get("first_name", "")
    last      = billing.get("last_name", "")  or customer.get("last_name", "")
    street    = billing.get("address1", "")
    city      = billing.get("city", "")
    state     = billing.get("province_code", "")
    zip_code  = billing.get("zip", "")
    country   = billing.get("country_code", "US")

    order_value   = float(order.get("total_price", 0))
    currency      = order.get("currency", "USD")
    created_at    = order.get("created_at", "")  # ISO8601
    order_name    = order.get("name", "")
    order_number  = str(order.get("order_number", ""))

    if not email:
        print(f"  SKIP {order_name}: no email found")
        return False

    # Build user identifiers
    user_identifiers = [
        {"hashedEmail": sha256(email)}
    ]
    if phone:
        # Normalize: strip non-digits, ensure E.164 format
        digits = "".join(c for c in phone if c.isdigit())
        if digits and not digits.startswith("1"):
            digits = "1" + digits
        user_identifiers.append({"hashedPhoneNumber": sha256(f"+{digits}")})
    if first and last:
        user_identifiers.append({
            "addressInfo": {
                "hashedFirstName": sha256(first),
                "hashedLastName":  sha256(last),
                "hashedStreetAddress": sha256(street) if street else None,
                "city":    city,
                "state":   state,
                "postalCode": zip_code,
                "countryCode": country,
            }
        })
        # Remove None values
        addr = user_identifiers[-1]["addressInfo"]
        user_identifiers[-1]["addressInfo"] = {k: v for k, v in addr.items() if v}

    conversion_resource = f"customers/{CUSTOMER_ID}/conversionActions/{conversion_action_id}"

    payload = {
        "conversions": [
            {
                "conversionAction": conversion_resource,
                "conversionDateTime": created_at.replace("T", " ").replace("+00:00", "+0000").replace("Z", "+0000"),
                "conversionValue": order_value,
                "currencyCode": currency,
                "orderId": order_number,
                "userIdentifiers": user_identifiers,
            }
        ],
        "partialFailure": True,
        "validateOnly": False,
    }

    url = f"https://googleads.googleapis.com/v17/customers/{CUSTOMER_ID}:uploadClickConversions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "login-customer-id": CUSTOMER_ID,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.ok:
        body = resp.json()
        errors = body.get("partialFailureError", {})
        results = body.get("results", [])
        if errors:
            print(f"  PARTIAL ERROR {order_name}: {json.dumps(errors)[:300]}")
            return False
        print(f"  OK {order_name} | {email} | ${order_value} {currency} | conv_action={conversion_action_id}")
        print(f"     Identifiers sent: {[list(u.keys())[0] for u in user_identifiers]}")
        return True
    else:
        print(f"  ERROR {order_name}: {resp.status_code} {resp.text[:400]}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Enhanced Conversions uploader")
    parser.add_argument("--list-actions", action="store_true", help="List all conversion actions")
    parser.add_argument("--order",        type=str,           help="Process a single Shopify order ID")
    parser.add_argument("--backfill",     action="store_true", help="Backfill last 3 days of paid orders")
    args = parser.parse_args()

    print("Authenticating with Google Ads API...")
    token = get_ads_token()
    print("Auth OK\n")

    if args.list_actions:
        print("=== Conversion Actions ===")
        actions = list_conversion_actions(token)
        for a in actions:
            ca = a.get("conversionAction", {})
            print(f"  ID: {ca.get('id'):>12}  Status: {ca.get('status'):12}  "
                  f"Category: {ca.get('category'):20}  Name: {ca.get('name')}")
        print(f"\nTotal: {len(actions)} conversion actions")
        return

    if not PURCHASE_CONVERSION_ACTION_ID:
        print("ERROR: Set CONVERSION_ACTION_ID env var (run --list-actions first to find it)")
        sys.exit(1)

    if args.order:
        print(f"Processing single order: {args.order}")
        order = get_order(args.order)
        send_enhanced_conversion(token, order, PURCHASE_CONVERSION_ACTION_ID)
        return

    if args.backfill:
        print("Backfilling recent paid orders (last 3 days)...")
        orders = get_recent_paid_orders(days=3)
        print(f"Found {len(orders)} paid orders\n")
        ok = 0
        for order in orders:
            result = send_enhanced_conversion(token, order, PURCHASE_CONVERSION_ACTION_ID)
            if result:
                ok += 1
            time.sleep(0.5)
        print(f"\nDone: {ok}/{len(orders)} uploaded successfully")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
