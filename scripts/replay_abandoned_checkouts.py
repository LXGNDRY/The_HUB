#!/usr/bin/env python3
"""
replay_abandoned_checkouts.py — Legendary Branding

Retroactively fires Klaviyo "Checkout Started" events for all open (abandoned)
Shopify checkouts that have an email address. This enrolls them in the
"Abandoned Cart Reminder" Klaviyo flow (ID: VXj9x6) so they receive the
two-email win-back sequence (1hr delay + 24hr delay with COMEBACK10 code).

Events are fired against metric ID YdsnAF ("Checkout Started" — the exact
metric the flow is triggered on, sourced from Shopify native integration).

Usage:
  python scripts/replay_abandoned_checkouts.py            # dry run — print only
  python scripts/replay_abandoned_checkouts.py --send     # fire Klaviyo events

Required env vars:
  SHOPIFY_ADMIN_TOKEN     — Shopify Admin API token
  KLAVIYO_API_KEY         — Klaviyo private API key
  SHOPIFY_STORE_DOMAIN    — (optional) defaults to lngndny.myshopify.com
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
SHOPIFY_TOKEN  = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
SHOPIFY_DOMAIN = os.environ.get("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
KLAVIYO_KEY    = os.environ.get("KLAVIYO_API_KEY", "")
SHOPIFY_API_VER = "2026-04"
SHOPIFY_BASE    = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_API_VER}"
SHOPIFY_HEADERS = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json",
}
KLAVIYO_EVENTS_URL = "https://a.klaviyo.com/api/events/"
KLAVIYO_HEADERS = {
    "Authorization": f"Klaviyo-API-Key {KLAVIYO_KEY}",
    "revision": "2024-10-15",
    "Content-Type": "application/json",
}

# Flow trigger metric — Shopify native "Checkout Started" (metric YdsnAF)
CHECKOUT_STARTED_METRIC_ID = "YdsnAF"


def get_abandoned_checkouts():
    """Fetch all open (abandoned) checkouts from Shopify REST API."""
    checkouts = []
    url = f"{SHOPIFY_BASE}/checkouts.json"
    params = {"status": "open", "limit": 250}
    while url:
        resp = requests.get(url, headers=SHOPIFY_HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        checkouts.extend(data.get("checkouts", []))
        # Handle pagination via Link header
        link = resp.headers.get("Link", "")
        url = None
        params = {}
        if 'rel="next"' in link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.strip().split(";")[0].strip("<> ")
                    break
    return checkouts


def build_line_items(raw_items):
    """Extract line item fields needed by the Klaviyo email template."""
    result = []
    for item in raw_items[:10]:
        result.append({
            "title":         item.get("title", ""),
            "variant_title": item.get("variant_title") or "",
            "quantity":      item.get("quantity", 1),
            "price":         item.get("price", "0.00"),
            "image_url":     item.get("image_url", ""),
        })
    return result


def fire_klaviyo_event(email, checkout):
    """POST a 'Checkout Started' event to Klaviyo for the given checkout."""
    line_items = build_line_items(checkout.get("line_items", []))
    body = {
        "data": {
            "type": "event",
            "attributes": {
                "metric": {
                    "data": {
                        "type": "metric",
                        "id": CHECKOUT_STARTED_METRIC_ID,
                    }
                },
                "profile": {
                    "data": {
                        "type": "profile",
                        "attributes": {"email": email},
                    }
                },
                "properties": {
                    "checkout_id":  checkout.get("id"),
                    "checkout_url": checkout.get("abandoned_checkout_url", ""),
                    "total_price":  checkout.get("total_price", "0.00"),
                    "item_count":   len(line_items),
                    "line_items":   line_items,
                },
                "time": datetime.now(timezone.utc).isoformat(),
            },
        }
    }
    resp = requests.post(KLAVIYO_EVENTS_URL, headers=KLAVIYO_HEADERS, json=body)
    resp.raise_for_status()
    return resp.status_code


def main():
    parser = argparse.ArgumentParser(description="Replay abandoned checkouts into Klaviyo flow")
    parser.add_argument("--send", action="store_true", help="Actually fire Klaviyo events (default: dry run)")
    args = parser.parse_args()

    if not SHOPIFY_TOKEN:
        print("ERROR: SHOPIFY_ADMIN_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    if args.send and not KLAVIYO_KEY:
        print("ERROR: KLAVIYO_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    print(f"{'DRY RUN — ' if not args.send else ''}Fetching abandoned checkouts from Shopify...")
    checkouts = get_abandoned_checkouts()
    print(f"  Total open checkouts: {len(checkouts)}")

    with_email    = [c for c in checkouts if c.get("email")]
    without_email = [c for c in checkouts if not c.get("email")]

    print(f"  With email (will fire): {len(with_email)}")
    print(f"  Without email (skipped): {len(without_email)}")
    print()

    fired = 0
    errors = 0
    for c in with_email:
        email     = c["email"]
        total     = c.get("total_price", "0.00")
        n_items   = len(c.get("line_items", []))
        checkout_url = c.get("abandoned_checkout_url", "")
        print(f"  {'[DRY]' if not args.send else '[SEND]'} {email} — ${total} ({n_items} items) — {checkout_url[:60]}...")
        if args.send:
            try:
                status = fire_klaviyo_event(email, c)
                print(f"         ✓ HTTP {status}")
                fired += 1
            except Exception as e:
                print(f"         ✗ ERROR: {e}")
                errors += 1

    print()
    if args.send:
        print(f"Done. Fired: {fired} | Errors: {errors} | Skipped (no email): {len(without_email)}")
    else:
        print(f"Dry run complete. {len(with_email)} events would fire. Run with --send to execute.")


if __name__ == "__main__":
    main()
