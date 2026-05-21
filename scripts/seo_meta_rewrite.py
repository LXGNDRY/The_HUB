#!/usr/bin/env python3
"""
SEO Meta Rewrite — Legendary Branding
Writes optimized title tags and meta descriptions for all collections
and all 80 products via Shopify Admin API.
"""
import os, json, time, requests

TOKEN  = os.environ["SHOPIFY_ADMIN_TOKEN"]
DOMAIN = "lngndny.myshopify.com"
API_VER = "2024-10"
BASE    = f"https://{DOMAIN}/admin/api/{API_VER}"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

def put(path, payload):
    r = requests.put(f"{BASE}{path}", headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()

def rate():
    time.sleep(0.55)

# ── Collection meta rewrites ──────────────────────────────────────────────────
# Format: (id, handle, seo_title, seo_description)
COLLECTIONS = [
    (
        223735742617,
        "accessories-more",
        "Streetwear Accessories | Legendary Branding",
        "Shop premium streetwear accessories from Legendary Branding. Trucker hats, sunglasses, and finishing pieces built to complete any fit. Free shipping available."
    ),
    (
        226122236057,
        "hoodies-jackets",
        "Oversized Hoodies & Jackets | Legendary Branding",
        "Shop heavyweight oversized hoodies and jackets from Legendary Branding. 400–460GSM premium cotton, drop shoulder fits, and bold streetwear graphics. Free shipping available."
    ),
    (
        341840789657,
        "mens-collection",
        "Men's Streetwear Sets | Legendary Branding",
        "Shop matching streetwear sets and outfit bundles from Legendary Branding. Premium two-piece jogger sets, sweatsuit sets, and coordinated fits built for the streets."
    ),
    (
        233408757913,
        "shirts-tops",
        "Heavyweight Oversized T-Shirts | Legendary Branding",
        "Shop heavyweight oversized t-shirts from Legendary Branding. 250–285GSM boxy fit tees, graphic streetwear designs, and premium cotton construction. Free shipping available."
    ),
    # Smart collection
    (
        306630852761,
        "all-products",
        "New Drops | Legendary Branding Streetwear",
        "Shop the latest drops from Legendary Branding. New heavyweight tees, oversized hoodies, jogger sets, and streetwear accessories added regularly. Don't miss out."
    ),
]

print("=== Collection Meta Rewrites ===")
for col_id, handle, seo_title, seo_desc in COLLECTIONS:
    # Try custom collection first, then smart
    for endpoint in [f"/custom_collections/{col_id}.json", f"/smart_collections/{col_id}.json"]:
        try:
            key = "custom_collection" if "custom" in endpoint else "smart_collection"
            r = put(endpoint, {key: {
                "id": col_id,
                "metafields_global_title_tag": seo_title,
                "metafields_global_description_tag": seo_desc
            }})
            print(f"  ✅ {handle}")
            print(f"     title: {seo_title}")
            break
        except Exception as e:
            if "404" in str(e):
                continue
            print(f"  ❌ {handle}: {e}")
            break
    rate()

# ── Product meta rewrites ─────────────────────────────────────────────────────
# Load product list
with open("/home/user/workspace/products_for_seo.json") as f:
    products = json.load(f)

# Build SEO data per product
# Pattern: "{Descriptive Title} | Legendary Branding" (≤60 chars)
# Desc: "{What it is}, {key specs}, {brand promise}." (≤155 chars)
def make_seo(title, ptype, tags_str):
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    
    # Extract useful spec tags
    gsm = next((t for t in tags if "GSM" in t.upper() or "gsm" in t.lower()), "")
    fit = next((t for t in tags if any(w in t.lower() for w in ["oversized","boxy","loose","cropped","slim"])), "")
    material = next((t for t in tags if any(w in t.lower() for w in ["cotton","heavyweight","premium"])), "")
    
    # Build description
    specs = [s for s in [gsm, fit, material] if s]
    spec_str = ", ".join(specs[:2]) if specs else ""
    
    if spec_str:
        desc = f"Shop the {title} from Legendary Branding. {spec_str} streetwear {ptype.lower() if ptype else 'piece'} built for the streets. Free shipping available."
    else:
        desc = f"Shop the {title} from Legendary Branding. Premium streetwear {ptype.lower() if ptype else 'piece'} crafted for quality and style. Free shipping available."
    
    # SEO title — keep under 60 chars
    seo_title = f"{title} | Legendary Branding"
    if len(seo_title) > 60:
        # Shorten brand suffix
        seo_title = f"{title} | LB"
    
    # Cap description at 155
    if len(desc) > 155:
        desc = desc[:152] + "..."
    
    return seo_title, desc

print("\n=== Product Meta Rewrites ===")
patched = 0
errors = 0
for p in products:
    pid = p["id"]
    title = p["title"]
    ptype = p.get("product_type", "")
    tags = p.get("tags", "")
    
    seo_title, seo_desc = make_seo(title, ptype, tags)
    
    try:
        put(f"/products/{pid}.json", {"product": {
            "id": pid,
            "metafields_global_title_tag": seo_title,
            "metafields_global_description_tag": seo_desc
        }})
        patched += 1
        print(f"  ✅ [{patched}/80] {title[:50]}")
        print(f"       → {seo_title}")
    except Exception as e:
        errors += 1
        print(f"  ❌ {title}: {e}")
    rate()

print(f"\n{'='*50}")
print(f"Collections: {len(COLLECTIONS)} updated")
print(f"Products:    {patched} updated | {errors} errors")
