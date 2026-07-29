"""
fix_google_product_category.py

Batch backfill: write the google_product_category metafield on every Shopify
product so GMC receives the correct numeric Google taxonomy ID.

The metafield (namespace="google", key="google_product_category") is what
Shopify's Google channel surfaces to GMC as the google_product_category feed
attribute. Without it, GMC auto-classifies — often incorrectly — leading to
disapprovals and missing required attributes (size, color, gender for apparel).

Resolution:
  product.product_type → resolve_product_type() → resolve_gmc_category_id()
  → write metafield value (numeric ID string, e.g. "212")

Env vars:
  DRY_RUN=true   Print what would change; do not write to Shopify (default: false)
  SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET (or SHOPIFY_ADMIN_TOKEN)
"""

import os
import sys
import time
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("fix_google_product_category")

STORE_DOMAIN = os.getenv("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
API_VERSION = "2026-04"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

BASE_URL = f"https://{STORE_DOMAIN}/admin/api/{API_VERSION}"


def _get_token() -> str:
    if ADMIN_TOKEN:
        return ADMIN_TOKEN
    resp = requests.post(
        f"https://{STORE_DOMAIN}/admin/oauth/access_token",
        json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "client_credentials"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def main():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from modules.product_compliance import resolve_product_type, resolve_gmc_category_id

    token = _get_token()
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    if DRY_RUN:
        logger.info("DRY RUN — no writes will occur")

    updated = 0
    skipped = 0
    errors = 0
    page_info = None

    while True:
        params = {"limit": 250, "fields": "id,title,product_type"}
        if page_info:
            params["page_info"] = page_info

        resp = requests.get(f"{BASE_URL}/products.json", headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        products = resp.json().get("products", [])

        if not products:
            break

        for p in products:
            product_id = p["id"]
            title = p.get("title", "")
            raw_type = (p.get("product_type") or "").strip()

            canonical = resolve_product_type(raw_type, title)
            category_id = resolve_gmc_category_id(canonical)

            # Check existing metafield
            mf_resp = requests.get(
                f"{BASE_URL}/products/{product_id}/metafields.json",
                headers=headers,
                params={"namespace": "google", "key": "google_product_category"},
                timeout=15,
            )
            mf_resp.raise_for_status()
            existing_mfs = mf_resp.json().get("metafields", [])
            existing_value = existing_mfs[0]["value"] if existing_mfs else ""

            if existing_value == category_id:
                logger.debug("SKIP %s (%s) — already %s", title[:50], product_id, category_id)
                skipped += 1
                continue

            action = f"{'(DRY) ' if DRY_RUN else ''}SET google_product_category={category_id} on '{title[:50]}' (was '{existing_value or 'blank'}')"
            logger.info(action)

            if not DRY_RUN:
                write_resp = requests.post(
                    f"{BASE_URL}/products/{product_id}/metafields.json",
                    headers=headers,
                    json={"metafield": {
                        "namespace": "google",
                        "key": "google_product_category",
                        "value": category_id,
                        "type": "single_line_text_field",
                    }},
                    timeout=15,
                )
                if write_resp.status_code in (200, 201):
                    updated += 1
                else:
                    logger.error("ERROR %s: %s %s", product_id, write_resp.status_code, write_resp.text[:200])
                    errors += 1
            else:
                updated += 1

            time.sleep(0.25)

        # Pagination via Link header
        link_header = resp.headers.get("Link", "")
        if 'rel="next"' in link_header:
            import re
            m = re.search(r'page_info=([^&>]+)[^>]*>;\s*rel="next"', link_header)
            page_info = m.group(1) if m else None
        else:
            page_info = None

        if not page_info:
            break

    logger.info("Done. updated=%d skipped=%d errors=%d%s", updated, skipped, errors, " (DRY RUN)" if DRY_RUN else "")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
