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
# ─────────────────────────────────────────────────────────────
REWRITES = {
    "running-shoes-ultra-light-racing-shoes-for-marathon-training-high-energy-cushioning-men-women": {
        "title": "LB Lightweight Performance Running Shoes",
        "seo_title": "LB Lightweight Performance Running Shoes | Legendary Branding",
        "seo_description": "Ultra-light, cushioned running shoes built for speed and endurance. High-energy foam sole for men and women. Shop Legendary Branding.",
    },
    "american-spider-pattern-embroidery-zip-up-hoodie-y2k-mens-womens-gothic-harajuku-jacket-fashion-hoodie-sweatshirt-casual-clothes": {
        "title": "Spider Pattern Embroidered Zip-Up Hoodie",
        "seo_title": "Spider Pattern Embroidered Zip-Up Hoodie | Legendary Branding",
        "seo_description": "Bold spider embroidery zip-up hoodie with a streetwear edge. Y2K-inspired unisex fit. Shop the latest drops at Legendary Branding.",
    },
    "autumn-tan-leopard-jeans-men-denim-pants-male-oversize-wide-leg-trousers": {
        "title": "LB Leopard Print Wide-Leg Denim Pants",
        "seo_title": "LB Leopard Print Wide-Leg Denim Pants | Legendary Branding",
        "seo_description": "Oversized wide-leg denim in a tan leopard print. Retro streetwear statement piece for men. Shop Legendary Branding.",
    },
    "womens-2-piece-stylish-outfits-long-sleeve-floral-embroidered-sweatshirt-solid-color-jogger-pants-sets": {
        "title": "LB Floral Embroidered Sweatshirt & Jogger Set",
        "seo_title": "LB Floral Embroidered Sweatshirt & Jogger Set | Legendary Branding",
        "seo_description": "Women's 2-piece set featuring a long-sleeve floral embroidered sweatshirt with matching solid jogger pants. Shop Legendary Branding.",
    },
    "mens-business-casual-short-sleeved-solid-color-polo-shirt-fashion-breathable-comfortable-summer-versatile-top": {
        "title": "LB Solid Breathable Polo Shirt",
        "seo_title": "LB Solid Breathable Polo Shirt | Legendary Branding",
        "seo_description": "Men's short-sleeve polo in a clean solid colorway. Breathable, versatile streetwear-meets-casual style. Shop Legendary Branding.",
    },
    "mens-modern-minimalist-pure-cotton-long-sleeved-lounge-set": {
        "title": "LB Cotton Minimalist Long-Sleeve Lounge Set",
        "seo_title": "LB Cotton Minimalist Long-Sleeve Lounge Set | Legendary Branding",
        "seo_description": "Men's pure cotton long-sleeve lounge set with a clean minimalist aesthetic. Comfortable everyday wear from Legendary Branding.",
    },
    "2025-new-retro-y2k-casual-two-piece-american-street-harajuku-sweatshirt-straight-trousers-men-casual-fashion-hoodie-streetwear": {
        "title": "LB Y2K Hoodie & Straight Trousers Set",
        "seo_title": "LB Y2K Hoodie & Straight Trousers Set | Legendary Branding",
        "seo_description": "Men's two-piece Y2K streetwear set — relaxed hoodie and straight-leg trousers. Retro American street style by Legendary Branding.",
    },
    "loose-straight-wide-leg-retro-casual-streetwear-three-stripes-jeans-high-stretch-denim-jeans-pant-for-women": {
        "title": "LB Three-Stripe Wide-Leg Stretch Jeans",
        "seo_title": "LB Three-Stripe Wide-Leg Stretch Jeans | Legendary Branding",
        "seo_description": "Women's high-stretch wide-leg denim jeans with a signature three-stripe detail. Retro streetwear fit from Legendary Branding.",
    },
    "men-denim-fashion-rhine-stone-straight-leg-men-stacked-denim-layered-jeans": {
        "title": "LB Rhinestone Stacked Straight Denim",
        "seo_title": "LB Rhinestone Stacked Straight Denim | Legendary Branding",
        "seo_description": "Men's straight-leg stacked denim with rhinestone detailing. Statement streetwear jeans from Legendary Branding.",
    },
    "five-pointed-star-p-letter-embroidery-side-7-baseball-caps-spring-autumn-outdoor-adjustable-casual-hats-sunscreen-hat": {
        "title": "LB Star P-Letter Embroidered Baseball Cap",
        "seo_title": "LB Star P-Letter Embroidered Baseball Cap | Legendary Branding",
        "seo_description": "Adjustable baseball cap with five-pointed star and P-letter embroidery. Clean streetwear accessory from Legendary Branding.",
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
