"""
fix_product_weights.py

Batch backfill: set a default weight (grams) on every Shopify product variant
that currently has no weight (weight == 0 or null).

Weight is inferred from the product's product_type → canonical taxonomy string →
WEIGHT_MAP_G in modules/product_compliance.py. Only writes to variants where
weight is missing — never overwrites an existing non-zero weight.

Env vars:
  DRY_RUN=true   Print what would change; do not write (default: false)
  SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET
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
CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
API_VERSION = "2026-04"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

BASE_URL = f"https://{STORE_DOMAIN}/admin/api/{API_VERSION}"
GRAPHQL_URL = f"https://{STORE_DOMAIN}/admin/api/{API_VERSION}/graphql.json"


def _get_token() -> str:
    resp = requests.post(
        f"https://{STORE_DOMAIN}/admin/oauth/access_token",
        data={
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

    FETCH_QUERY = """
    query($cursor: String) {
      products(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          title
          productType
          variants(first: 50) {
            nodes { id weight weightUnit }
          }
        }
      }
    }
    """

    UPDATE_MUTATION = """
    mutation updateVariantWeight($input: ProductVariantInput!) {
      productVariantUpdate(input: $input) {
        productVariant { id weight weightUnit }
        userErrors { field message }
      }
    }
    """

    updated = 0
    skipped = 0
    errors = 0
    cursor = None

    while True:
        resp = requests.post(
            GRAPHQL_URL,
            headers=headers,
            json={"query": FETCH_QUERY, "variables": {"cursor": cursor}},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("products", {})

        for product in data.get("nodes", []):
            title = product.get("title", "")
            raw_type = (product.get("productType") or "").strip()
            canonical = resolve_product_type(raw_type, title)
            weight_g = resolve_product_weight_g(canonical)

            for variant in product["variants"]["nodes"]:
                current = float(variant.get("weight") or 0)
                if current > 0:
                    skipped += 1
                    continue

                action = (
                    f"{'(DRY) ' if DRY_RUN else ''}"
                    f"SET weight={weight_g:.0f}g on variant {variant['id'].split('/')[-1]} "
                    f"of '{title[:50]}' [{canonical.split('>')[-1].strip()}]"
                )
                logger.info(action)

                if not DRY_RUN:
                    mut_resp = requests.post(
                        GRAPHQL_URL,
                        headers=headers,
                        json={
                            "query": UPDATE_MUTATION,
                            "variables": {
                                "input": {
                                    "id": variant["id"],
                                    "weight": weight_g,
                                    "weightUnit": "GRAMS",
                                }
                            },
                        },
                        timeout=15,
                    )
                    mut_resp.raise_for_status()
                    errs = (
                        mut_resp.json()
                        .get("data", {})
                        .get("productVariantUpdate", {})
                        .get("userErrors", [])
                    )
                    if errs:
                        logger.error("ERROR variant %s: %s", variant["id"], errs)
                        errors += 1
                    else:
                        updated += 1
                else:
                    updated += 1

                time.sleep(0.2)

        page_info = data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]

    logger.info(
        "Done. updated=%d skipped=%d errors=%d%s",
        updated, skipped, errors, " (DRY RUN)" if DRY_RUN else "",
    )
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
