#!/usr/bin/env python3
"""
touch_products_indexnow.py
Does a lightweight no-op update (tags touch) on all unindexed LB products.
This triggers Shopify's native IndexNow integration, which automatically
pings Bing, Yandex, and Google's IndexNow endpoint for each product URL.
"""
import os, json, time, requests

SHOP = "lngndny.myshopify.com"
TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
API = f"https://{SHOP}/admin/api/2024-10"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

HANDLES = [
    "legendary-x-champion-r-simple-sweatshirt", "butterfly-tee", "ghosted-tee",
    "legendary-x-adidas-sport-polo-recycled-pique-hydrophilic-finish",
    "athletic-department-premium-tank-top-soft-washed-cotton-relaxed-fit",
    "legendary-world-round-t-shirt", "yellow-dot-athletic-long-short",
    "goat-denim-t-shirt-lightweight-cotton-tee-soft-touch-streetwear-fit",
    "legendary-distressed-sweatshirt-washed-ombre-effect-heavyweight-440",
    "mentality-matters2-heavyweight-washed-boxy-hoodie",
    "mentality-matters2-unisex-boxy-t-shirt", "mountain-trek-unisex-boxy-t-shirt",
    "goat-club-syracuse-trucker-hat", "goat-club-texas-trucker-hat",
    "foam-trucker-hat-with-mesh-panels", "goat-club-atlanta-trucker-hat",
    "goat-club-chicago-trucker-hat", "unisex-oversized-snow-wash-t-shirt285gsm-2",
    "unisex-boxy-t-shirt280gsm", "hysteria-cropped-boxy-tank-top-280gsm-1",
    "summer-vibes-cropped-boxy-tank-top-280gsm",
    "240gsm-unisex-oversized-drop-shoulders-t-shirt",
    "santa-barbara-oversized-crewneck-sweatshirt-460gsm",
    "rose-bowl-oversized-crewneck-sweatshirt-460gsm", "the-lb-hat-foam-trucker-hat",
    "goat-wrld-loose-fit-t-shirt-190gsm", "goat-sh-t-only-oversized-cropped-t-shirt280gsm",
    "legendary-fx-oversized-cropped-t-shirt280gsm", "stay-rich-oversized-t-shirt190-gsm",
    "land-of-the-goated-oversized-t-shirt190-gsm",
    "legendary-coast-club-oversized-t-shirt190-gsm",
    "blank-oversized-snow-wash-t-shirt", "blank-washed-gradient-goat-t-shirt",
    "blank-washed-gradient-t-shirt",
    "bottom-sunfade-gradient-washed-vintage-goat-t-shirt250gsm",
    "cropped-snow-washed-goat-t-shirt285gsm", "goat-casual-sweat-shorts280gsm",
    "goat-speed-boxy-fit-hoodie400gsm", "oversized-heavyweight-hoodie-goat-club-drip",
    "goated-oversized-heavyweight-sweatshirt-unisex-fleece-crewneck-bold-streetwear-pullover-soft-cotton-blend-cozy-relaxed-fit-drop-shoulder-hoodie-alt",
    "lil-goat-combed-cotton-regular-fit-t-shirt190gsm",
    "the-goat-combed-cotton-regular-fit-t-shirt190gsm",
    "goat-varsity-club-cotton-regular-fit-t-shirt190gsm",
    "mens-solid-color-oversized-hoodie-jogger-set",
    "striped-flared-sweatpants-mens-slim-fit-sweatpants",
    "jeans-men-new-streetwear-baggy-wide-leg-jeans-korean-fashion",
    "faith-oversized-drop-shoulders-t-shirt", "legendary-wide-leg-sweatpants",
    "the-goat-premium-polo", "shattered-backboard-oversized-t-shirt190-gsm",
    "goat-society-chosen-one-oversized-t-shirt190-gsm",
    "adistar-jellyfish-oversized-t-shirt", "goat-club-oversized-t-shirt",
    "neverdy-oversized-t-shirt-235gsm", "neverdy-boxy-fit-hoodie",
    "heavyweight-oversized-hoodie-460gsm", "heavyweight-multi-pocket-jean",
    "legendary-branding-heavyweight-sweatpants-440gsm",
    "legendary-branding-fleece-zip-up", "goat-hoodie-440gsm",
    "no-risk-no-story-oversized-t-shirt", "mini-goat-oversized-t-shirt",
    "goat-club-spray-painted-oversized-hoodie",
    "legendary-branding-og-permanent-marker-t-shirt-unisex-heavyweight-40s-combed-cotton-oversized-t-shirt-235gsm",
    "dawg-pit-bull-oversized-t-shirt",
    "icon-of-the-herd-combed-cotton-cropped-oversized-t-shirt-250gsm",
    "the-legendary-heavyweight-oversized-t-shirt",
]

results = {"ok": [], "error": []}
print(f"Touching {len(HANDLES)} products to trigger Shopify IndexNow...\n{'='*60}")

for handle in HANDLES:
    # 1. Fetch the product by handle
    r = requests.get(f"{API}/products.json?handle={handle}&fields=id,tags", headers=HEADERS)
    if r.status_code != 200 or not r.json().get("products"):
        print(f"  ✗ NOT FOUND: {handle}")
        results["error"].append(handle)
        time.sleep(0.5)
        continue

    product = r.json()["products"][0]
    pid = product["id"]
    existing_tags = product.get("tags", "")

    # 2. No-op update: set tags to exactly what they already are
    # This marks the product as updated → triggers IndexNow ping
    patch = requests.put(
        f"{API}/products/{pid}.json",
        headers=HEADERS,
        json={"product": {"id": pid, "tags": existing_tags}}
    )

    if patch.status_code == 200:
        print(f"  ✓ touched: {handle}")
        results["ok"].append(handle)
    else:
        print(f"  ✗ ERROR {patch.status_code}: {handle} — {patch.text[:100]}")
        results["error"].append(handle)

    time.sleep(0.6)  # stay under 2 req/s Shopify REST limit

print(f"\n{'='*60}")
print(f"Done — touched: {len(results['ok'])} | errors: {len(results['error'])}")
if results["error"]:
    print("Errors:", results["error"])
