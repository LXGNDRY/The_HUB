#!/usr/bin/env python3
"""
product_title_cleanup.py
Rewrites AliExpress-style product titles + SEO meta to brand-aligned
Legendary Branding names. Targets 10 specific products identified via
Search Console as pulling wrong international traffic.

Usage:
    python scripts/product_title_cleanup.py [--dry-run]
"""

import os
import sys
import json
import time
import argparse
import requests

SHOP = "lngndny.myshopify.com"
API_VERSION = "2024-01"
TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]

HEADERS = {
    "X-Shopify-Access-Token": TOKEN,
    "Content-Type": "application/json",
}

# ─────────────────────────────────────────────────────────────
# Brand-aligned rewrites
# handle → { title, seo_title, seo_description }
#
# v2: Updated to actual Shopify handles (confirmed via handle dump).
# 8 original SC handles were 404s (products deleted from store).
# These 8 handles target the AliExpress-style products still active.
# ─────────────────────────────────────────────────────────────
REWRITES = {
    # Already updated in v1 run
    "womens-2-piece-stylish-outfits-long-sleeve-floral-embroidered-sweatshirt-solid-color-jogger-pants-sets": {
        "title": "LB Bow Embroidered Hoodie & Jogger Set",
        "seo_title": "LB Bow Embroidered Hoodie & Jogger Set | Legendary Branding",
        "seo_description": "Women's 2-piece set featuring a bow embroidered hoodie and matching jogger pants. Clean streetwear style from Legendary Branding.",
    },
    "men-denim-fashion-rhine-stone-straight-leg-men-stacked-denim-layered-jeans": {
        "title": "LB Rhinestone Stacked Straight Denim",
        "seo_title": "LB Rhinestone Stacked Straight Denim | Legendary Branding",
        "seo_description": "Men's straight-leg stacked denim with rhinestone detailing. Statement streetwear jeans from Legendary Branding.",
    },
    # v2 additions — real handles confirmed from store
    "2-pieces-classic-mens-sportswear-set-soft-breathable-full-zip-tracksuit": {
        "title": "LB Full-Zip Tracksuit Set",
        "seo_title": "LB Full-Zip Tracksuit Set | Legendary Branding",
        "seo_description": "Men's soft, breathable full-zip tracksuit. Classic two-piece sportswear with a streetwear edge. Shop Legendary Branding.",
    },
    "cycling-sunglasses-uv-protect-glasses-outdoor-mtb-bike-shades-sports-fishing-glasses": {
        "title": "LB UV Sport Sunglasses",
        "seo_title": "LB UV Sport Sunglasses | Legendary Branding",
        "seo_description": "UV-protective sport sunglasses. Lightweight, durable, and built for outdoor wear. Shop accessories at Legendary Branding.",
    },
    "2025-new-hip-hop-fashion-spliced-baggy-jeans-for-men-pleated-design-casual-straight-leg-denim-pants-y2k-vintage-streetwear-jean": {
        "title": "LB Spliced Baggy Streetwear Jeans",
        "seo_title": "LB Spliced Baggy Streetwear Jeans | Legendary Branding",
        "seo_description": "Men's baggy spliced denim with a pleated design and straight-leg fit. Y2K-inspired streetwear denim from Legendary Branding.",
    },
    "jeans-men-new-streetwear-baggy-wide-leg-jeans-korean-fashion": {
        "title": "LB Baggy Wide-Leg Denim",
        "seo_title": "LB Baggy Wide-Leg Denim | Legendary Branding",
        "seo_description": "Men's wide-leg baggy jeans with a relaxed streetwear fit. Clean, oversized denim from Legendary Branding.",
    },
    "jacket-mens-corduroy-korean-version-casual-fashion-loose-lapel-mens": {
        "title": "LB Corduroy Lapel Jacket",
        "seo_title": "LB Corduroy Lapel Jacket | Legendary Branding",
        "seo_description": "Men's loose corduroy lapel jacket. Casual, textured outerwear with a streetwear-meets-classic style. Shop Legendary Branding.",
    },
    "men-s-solid-color-oversized-hoodie-jogger-set": {
        "title": "LB Oversized Hoodie & Jogger Set",
        "seo_title": "LB Oversized Hoodie & Jogger Set | Legendary Branding",
        "seo_description": "Men's solid color oversized hoodie and jogger matching set. Clean, comfortable streetwear from Legendary Branding.",
    },
    "casual-pants-striped-flared-sweatpants-new-mens-slim-fit-pants": {
        "title": "LB Striped Flare Sweatpants",
        "seo_title": "LB Striped Flare Sweatpants | Legendary Branding",
        "seo_description": "Men's striped flared sweatpants with a slim-to-flare silhouette. Bold streetwear bottoms from Legendary Branding.",
    },
    "belt-cropped-trench-spring-jacket-women-vintage-streetwear-double-breasted-long-sleeve-top-female-coat-outfits": {
        "title": "LB Belted Cropped Trench Jacket",
        "seo_title": "LB Belted Cropped Trench Jacket | Legendary Branding",
        "seo_description": "Women's double-breasted belted cropped trench jacket. Vintage-inspired streetwear outerwear from Legendary Branding.",
    },
}


def get_all_products():
    """Fetch all products from Shopify Admin API with pagination."""
    products = []
    url = f"https://{SHOP}/admin/api/{API_VERSION}/products.json"
    params = {"limit": 250, "status": "active", "fields": "id,title,handle"}

    while url:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("products", [])
        products.extend(batch)
        print(f"  Fetched {len(batch)} products (total so far: {len(products)})")

        # Handle pagination via Link header
        link = resp.headers.get("Link", "")
        url = None
        params = {}
        if 'rel="next"' in link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
                    break
        time.sleep(0.3)

    return products


def update_product(product_id, title, seo_title, seo_description, dry_run=False):
    """Update product title and SEO meta."""
    payload = {
        "product": {
            "id": product_id,
            "title": title,
            "metafields_global_title_tag": seo_title,
            "metafields_global_description_tag": seo_description,
        }
    }
    if dry_run:
        print(f"    [DRY RUN] Would update ID {product_id}: {title}")
        return True

    url = f"https://{SHOP}/admin/api/{API_VERSION}/products/{product_id}.json"
    resp = requests.put(url, headers=HEADERS, json=payload)
    if resp.status_code == 200:
        updated = resp.json().get("product", {})
        print(f"    ✓ Updated: {updated.get('title')}")
        return True
    else:
        print(f"    ✗ Error {resp.status_code}: {resp.text[:200]}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Product title cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    dry_run = args.dry_run
    if dry_run:
        print("=== DRY RUN MODE — no changes will be written ===\n")

    print("Fetching all products from Shopify...")
    all_products = get_all_products()
    print(f"Total products fetched: {len(all_products)}\n")

    # Build handle → product map
    handle_map = {p["handle"]: p for p in all_products if p.get("handle")}

    results = {"updated": [], "not_found": [], "errors": []}

    for handle, rewrite in REWRITES.items():
        print(f"Processing: {handle[:60]}...")
        product = handle_map.get(handle)

        if not product:
            print(f"  ✗ NOT FOUND in store (handle may have changed)")
            results["not_found"].append(handle)
            continue

        pid = product["id"]
        old_title = product["title"]
        new_title = rewrite["title"]
        print(f"  Old title: {old_title}")
        print(f"  New title: {new_title}")

        success = update_product(
            pid,
            new_title,
            rewrite["seo_title"],
            rewrite["seo_description"],
            dry_run=dry_run,
        )
        if success:
            results["updated"].append({"id": pid, "handle": handle, "old": old_title, "new": new_title})
        else:
            results["errors"].append(handle)

        time.sleep(0.5)  # Shopify rate limit

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"  Updated:   {len(results['updated'])}")
    print(f"  Not found: {len(results['not_found'])}")
    print(f"  Errors:    {len(results['errors'])}")

    if results["not_found"]:
        print("\nNot found handles:")
        for h in results["not_found"]:
            print(f"  - {h}")

    if results["errors"]:
        print("\nFailed handles:")
        for h in results["errors"]:
            print(f"  - {h}")
        sys.exit(1)

    if not dry_run and results["updated"]:
        print("\nSuccessfully updated products:")
        for r in results["updated"]:
            print(f"  [{r['id']}] {r['old']} → {r['new']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
