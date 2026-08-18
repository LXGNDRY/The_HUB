"""
fix_product_weights.py

Batch backfill: set a default weight (grams) on every Shopify product variant
that currently has no weight (weight == 0 or null).

Uses the REST API throughout — GraphQL's ProductVariant type no longer exposes
weight/weightUnit fields in API 2026-04+.

Weight is inferred from the product's product_type → canonical taxonomy string →
WEIGHT_MAP_G in modules/product_compliance.py. Only writes to variants where
weight is missing — never overwrites an existing non-zero weight.

Env vars:
  DRY_RUN=true   Print what would change; do not write (default: false)
  SHOPIFY_ADMIN_TOKEN         (preferred — long-lived admin token)
  SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET  (fallback OAuth client credentials)
  SHOPIFY_STORE_DOMAIN  (default: lngndny.myshopify.com)
"""

import os
import sys
import time
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("fix_product_weights")

STORE_DOMAIN = os.getenv("SHOPIFY_STORE_DOMAIN") or "lngndny.myshopify.com"
ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
API_VERSION = "2026-04"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

BASE_URL = f"https://{STORE_DOMAIN}/admin/api/{API_VERSION}"


def _get_token() -> str:
    if ADMIN_TOKEN:
        return ADMIN_TOKEN
    resp = requests.post(
        f"https://{STORE_DOMAIN}/admin/oauth/access_token",
        json={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def main():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from modules.product_compliance import resolve_product_type, resolve_product_weight_g

    token = _get_token()
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    if DRY_RUN:
        logger.info("DRY RUN — no writes will occur")

    updated = 0
    skipped = 0
    errors = 0

    # REST pagination via Link header
    url = f"{BASE_URL}/products.json"
    params = {"limit": 250, "status": "any", "fields": "id,title,product_type,variants"}

    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        products = resp.json().get("products", [])
        params = None  # only used on first request

        for product in products:
            title = product.get("title", "")
            raw_type = (product.get("product_type") or "").strip()
            canonical = resolve_product_type(raw_type, title)
            weight_g = resolve_product_weight_g(canonical)

            for variant in product.get("variants", []):
                current = float(variant.get("weight") or 0)
                if current > 0:
                    skipped += 1
                    continue

                action = (
                    f"{'(DRY) ' if DRY_RUN else ''}"
                    f"SET weight={weight_g:.0f}g on variant {variant['id']} "
                    f"of '{title[:50]}' [{canonical.split('>')[-1].strip()}]"
                )
                logger.info(action)

                if not DRY_RUN:
                    put_resp = requests.put(
                        f"{BASE_URL}/variants/{variant['id']}.json",
                        headers=headers,
                        json={"variant": {"id": variant["id"], "weight": weight_g, "weight_unit": "g"}},
                        timeout=15,
                    )
                    if put_resp.status_code >= 400:
                        logger.error("ERROR variant %s: HTTP %s %s", variant["id"], put_resp.status_code, put_resp.text[:200])
                        errors += 1
                    else:
                        updated += 1
                else:
                    updated += 1

                time.sleep(0.2)

        # Follow REST pagination Link header
        link = resp.headers.get("Link", "")
        next_url = None
        for part in link.split(","):
            part = part.strip()
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip().strip("<>")
                break
        url = next_url

    logger.info(
        "Done. updated=%d skipped=%d errors=%d%s",
        updated, skipped, errors, " (DRY RUN)" if DRY_RUN else "",
    )
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
