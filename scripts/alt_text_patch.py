#!/usr/bin/env python3
"""
Alt Text Bulk Patch — Legendary Branding
Audits all product images and patches any missing alt text using
product title + type + position context.

Usage:
  SHOPIFY_ADMIN_TOKEN=shpat_... SHOPIFY_STORE_DOMAIN=lngndny.myshopify.com python3 alt_text_patch.py

GitHub Actions: uses SHOPIFY_ADMIN_TOKEN and SHOPIFY_STORE_DOMAIN secrets.
"""

import os
import sys
import json
import time
import requests

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN  = os.environ["SHOPIFY_ADMIN_TOKEN"]
DOMAIN = os.environ.get("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
API_VER = "2024-10"
BASE    = f"https://{DOMAIN}/admin/api/{API_VER}"
HEADERS = {
    "X-Shopify-Access-Token": TOKEN,
    "Content-Type": "application/json",
}
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

# ── Helpers ───────────────────────────────────────────────────────────────────
def shopify_get(path, params=None):
    r = requests.get(f"{BASE}{path}", headers=HEADERS, params=params or {})
    r.raise_for_status()
    return r.json()

def shopify_put(path, payload):
    r = requests.put(f"{BASE}{path}", headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()

def rate_limit():
    """Shopify REST: 2 req/sec (leaky bucket 40). Sleep 0.55s to stay safe."""
    time.sleep(0.55)

# ── Alt text generator ────────────────────────────────────────────────────────
def generate_alt(title: str, product_type: str, position: int, tags: str = "") -> str:
    """
    Build a descriptive, SEO-friendly alt text from product metadata.
    Pattern: "{Title} — {Type} | Legendary Branding"
    For position > 1: "{Title} — {Type} Detail View {position} | Legendary Branding"
    """
    # Clean inputs
    title = title.strip()
    ptype = product_type.strip() if product_type else ""

    # Pull a useful tag if present (color, style hints)
    tag_hints = []
    for tag in (tags or "").split(","):
        tag = tag.strip().lower()
        # Only use short, descriptive tags (skip generic ones)
        if tag and len(tag) < 20 and tag not in ("new", "sale", "featured", "all", ""):
            tag_hints.append(tag.title())
        if len(tag_hints) >= 1:
            break

    hint = f" — {tag_hints[0]}" if tag_hints else ""

    if position == 1:
        if ptype:
            return f"{title}{hint} — {ptype} | Legendary Branding"
        return f"{title}{hint} | Legendary Branding"
    else:
        if ptype:
            return f"{title} — {ptype} Detail View {position} | Legendary Branding"
        return f"{title} Detail View {position} | Legendary Branding"

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Legendary Branding — Alt Text Bulk Patch")
    print(f"Store: {DOMAIN}  |  DRY_RUN: {DRY_RUN}")
    print("=" * 60)

    # 1. Fetch all active products (paginated)
    all_products = []
    params = {"limit": 250, "status": "active", "fields": "id,title,product_type,tags,images"}
    while True:
        resp = shopify_get("/products.json", params)
        batch = resp.get("products", [])
        all_products.extend(batch)
        print(f"  Fetched {len(all_products)} products so far...")
        # Check for next page link header (pagination)
        # Simple single-page for <=250; if >250 we'd need cursor pagination
        if len(batch) < 250:
            break
        # cursor pagination not needed — store has 80 products
        break

    print(f"\nTotal products: {len(all_products)}")

    # 2. Audit
    missing = []
    total_images = 0
    for p in all_products:
        for img in p.get("images", []):
            total_images += 1
            alt = (img.get("alt") or "").strip()
            if not alt:
                missing.append({
                    "product_id": p["id"],
                    "product_title": p["title"],
                    "product_type": p.get("product_type", ""),
                    "tags": p.get("tags", ""),
                    "image_id": img["id"],
                    "position": img.get("position", 1),
                    "generated_alt": generate_alt(
                        p["title"],
                        p.get("product_type", ""),
                        img.get("position", 1),
                        p.get("tags", ""),
                    )
                })

    print(f"Total images:       {total_images}")
    print(f"Missing alt text:   {len(missing)}")
    print(f"Already have alt:   {total_images - len(missing)}")

    if not missing:
        print("\n✅ All images already have alt text. Nothing to patch.")
        return

    # 3. Preview first 10
    print("\nSample patches (first 10):")
    for m in missing[:10]:
        print(f"  [{m['product_id']}] {m['product_title']} img#{m['image_id']} pos:{m['position']}")
        print(f"    → \"{m['generated_alt']}\"")

    if DRY_RUN:
        print(f"\n[DRY RUN] Would patch {len(missing)} images. Set DRY_RUN=false to apply.")
        # Save report
        with open("alt_text_report.json", "w") as f:
            json.dump({"total_images": total_images, "missing": missing}, f, indent=2)
        print("Report saved to alt_text_report.json")
        return

    # 4. Patch
    print(f"\nPatching {len(missing)} images...")
    patched = 0
    errors = 0
    for m in missing:
        try:
            shopify_put(
                f"/products/{m['product_id']}/images/{m['image_id']}.json",
                {"image": {"id": m["image_id"], "alt": m["generated_alt"]}}
            )
            patched += 1
            print(f"  ✅ [{patched}/{len(missing)}] {m['product_title']} pos:{m['position']}")
            rate_limit()
        except Exception as e:
            errors += 1
            print(f"  ❌ FAILED [{m['product_id']}] img {m['image_id']}: {e}")

    # 5. Summary
    print("\n" + "=" * 60)
    print(f"DONE — Patched: {patched}  |  Errors: {errors}")
    print("=" * 60)

    # Save report
    with open("alt_text_report.json", "w") as f:
        json.dump({
            "total_images": total_images,
            "total_missing": len(missing),
            "patched": patched,
            "errors": errors,
            "patches": missing,
        }, f, indent=2)
    print("Full report saved to alt_text_report.json")

    if errors > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
