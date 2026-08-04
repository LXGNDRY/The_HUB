#!/usr/bin/env python3
"""
register_webhooks.py — Legendary Branding

Idempotently registers all required Shopify webhook subscriptions pointing at
the gcp-bot Cloud Run service. Safe to run multiple times — existing topics
are skipped, missing ones are created.

Required env vars:
  SHOPIFY_ADMIN_TOKEN    — Shopify Admin API token
  APP_URL                — Public base URL of the gcp-bot service
                           e.g. https://gcp-bot-exy37drh4q-uc.a.run.app

Usage:
  python scripts/register_webhooks.py            # dry run — show what would change
  python scripts/register_webhooks.py --apply    # register missing webhooks
"""

import os
import sys
import argparse
import requests

SHOPIFY_TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
SHOPIFY_DOMAIN = os.environ.get("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
APP_URL = os.environ.get("APP_URL", "").rstrip("/")
SHOPIFY_API_VER = "2026-04"
BASE = f"https://{SHOPIFY_DOMAIN}/admin/api/{SHOPIFY_API_VER}"
HEADERS = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json",
}

# All topics the gcp-bot webhook router handles
REQUIRED_TOPICS = [
    "checkouts/create",
    "checkouts/update",
    "orders/paid",
    "orders/fulfilled",
    "products/create",
    "products/update",
]


def list_existing() -> dict:
    """Return a dict of {topic: webhook_id} for all currently registered webhooks."""
    resp = requests.get(f"{BASE}/webhooks.json", headers=HEADERS, params={"limit": 250})
    resp.raise_for_status()
    return {w["topic"]: w["id"] for w in resp.json().get("webhooks", [])}


def create_webhook(topic: str, address: str) -> dict:
    payload = {"webhook": {"topic": topic, "address": address, "format": "json"}}
    resp = requests.post(f"{BASE}/webhooks.json", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json().get("webhook", {})


def main():
    parser = argparse.ArgumentParser(description="Register Shopify webhooks for gcp-bot")
    parser.add_argument("--apply", action="store_true", help="Create missing webhooks (default: dry run)")
    args = parser.parse_args()

    if not SHOPIFY_TOKEN:
        print("ERROR: SHOPIFY_ADMIN_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    if not APP_URL:
        print("ERROR: APP_URL not set (e.g. https://gcp-bot-xxxxx-uc.a.run.app)", file=sys.stderr)
        sys.exit(1)

    target = f"{APP_URL}/webhooks/shopify"
    print(f"Target endpoint: {target}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print()

    existing = list_existing()
    print(f"Currently registered webhooks ({len(existing)}):")
    for topic, wid in existing.items():
        print(f"  {topic} (id={wid})")
    print()

    missing = [t for t in REQUIRED_TOPICS if t not in existing]
    already_ok = [t for t in REQUIRED_TOPICS if t in existing]
    extra = [t for t in existing if t not in REQUIRED_TOPICS]

    print(f"Already registered (no action): {already_ok or ['none']}")
    print(f"Missing (will register):        {missing or ['none']}")
    if extra:
        print(f"Extra (not managed here):       {extra}")
    print()

    if not missing:
        print("All required webhooks are already registered.")
        return

    for topic in missing:
        if args.apply:
            try:
                hook = create_webhook(topic, target)
                print(f"  ✓ Created {topic} → id={hook.get('id')}")
            except Exception as e:
                print(f"  ✗ Failed to create {topic}: {e}")
        else:
            print(f"  [DRY] Would create: {topic} → {target}")

    if not args.apply:
        print()
        print("Dry run complete. Run with --apply to register missing webhooks.")


if __name__ == "__main__":
    main()
