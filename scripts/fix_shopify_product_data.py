#!/usr/bin/env python3
"""
fix_shopify_product_data.py

1. Fill missing barcodes with SKU values (464 variants)
2. Fix 29 products with blank product type (inferred from title keywords)
3. Standardize all product types to Google Shopping taxonomy strings
"""
import os, requests, json, time, re

ADMIN_TOKEN   = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID     = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOP          = "lngndny.myshopify.com"
API_VERSION   = "2026-04"

if CLIENT_ID and CLIENT_SECRET:
    token_resp = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        json={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    )
    token_resp.raise_for_status()
    TOKEN = token_resp.json()["access_token"]
elif ADMIN_TOKEN:
    TOKEN = ADMIN_TOKEN
else:
    raise RuntimeError("Set SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET, or SHOPIFY_ADMIN_TOKEN.")
GQL_URL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

def gql(query, variables=None):
    r = requests.post(GQL_URL, headers=HEADERS, json={"query": query, "variables": variables or {}})
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        print(f"  [GQL error] {data['errors']}")
    return data

# ── Google Shopping taxonomy map ─────────────────────────────────────────────
# Maps current Shopify product type → canonical Google taxonomy string
TAXONOMY_MAP = {
    "T shirt":      "Apparel & Accessories > Clothing > Shirts & Tops",
    "T Shirt":      "Apparel & Accessories > Clothing > Shirts & Tops",
    "t shirt":      "Apparel & Accessories > Clothing > Shirts & Tops",
    "Hoodie":       "Apparel & Accessories > Clothing > Activewear > Hoodies",
    "Sweatshirt":   "Apparel & Accessories > Clothing > Activewear > Hoodies",
    "Jeans":        "Apparel & Accessories > Clothing > Pants",
    "Sweatpants":   "Apparel & Accessories > Clothing > Pants",
    "Shorts":       "Apparel & Accessories > Clothing > Shorts",
    "Hat":          "Apparel & Accessories > Clothing Accessories > Hats",
    "Tank Top":     "Apparel & Accessories > Clothing > Shirts & Tops",
    "Jacket":       "Apparel & Accessories > Clothing > Outerwear",
    "Outfit Set":   "Apparel & Accessories > Clothing > Outfit Sets",
    "Polo":         "Apparel & Accessories > Clothing > Shirts & Tops",
    "Tracksuit":    "Apparel & Accessories > Clothing > Outfit Sets",
    "Lounge Set":   "Apparel & Accessories > Clothing > Outfit Sets",
    "Sunglasses":   "Apparel & Accessories > Clothing Accessories > Sunglasses",
}

# ── Keyword rules for blank product types ────────────────────────────────────
def infer_product_type(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ["hoodie", "hooded"]):
        return "Apparel & Accessories > Clothing > Activewear > Hoodies"
    if any(k in t for k in ["sweatshirt", "crewneck", "fleece"]):
        return "Apparel & Accessories > Clothing > Activewear > Hoodies"
    if any(k in t for k in ["sweatpant", "jogger", "trackpant"]):
        return "Apparel & Accessories > Clothing > Pants"
    if any(k in t for k in ["jean", "denim pant"]):
        return "Apparel & Accessories > Clothing > Pants"
    if any(k in t for k in ["short"]):
        return "Apparel & Accessories > Clothing > Shorts"
    if any(k in t for k in ["tank", "muscle"]):
        return "Apparel & Accessories > Clothing > Shirts & Tops"
    if any(k in t for k in ["t-shirt", "t shirt", "tee", " tee ", "boxy t", "oversized t"]):
        return "Apparel & Accessories > Clothing > Shirts & Tops"
    if any(k in t for k in ["polo"]):
        return "Apparel & Accessories > Clothing > Shirts & Tops"
    if any(k in t for k in ["jacket", "windbreaker", "bomber"]):
        return "Apparel & Accessories > Clothing > Outerwear"
    if any(k in t for k in ["hat", "cap", "trucker", "beanie", "snapback"]):
        return "Apparel & Accessories > Clothing Accessories > Hats"
    if any(k in t for k in ["sunglass", "shades"]):
        return "Apparel & Accessories > Clothing Accessories > Sunglasses"
    if any(k in t for k in ["set", "tracksuit", "outfit", "lounge"]):
        return "Apparel & Accessories > Clothing > Outfit Sets"
    # Default fallback for ambiguous apparel
    return "Apparel & Accessories > Clothing > Shirts & Tops"

# ── Fetch all products ────────────────────────────────────────────────────────
FETCH_Q = """
query($cursor: String) {
  products(first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      title
      productType
      variants(first: 100) {
        nodes { id sku barcode }
      }
    }
  }
}
"""

print("Fetching all products...")
all_products = []
cursor = None
while True:
    data = gql(FETCH_Q, {"cursor": cursor})
    nodes = data["data"]["products"]["nodes"]
    all_products.extend(nodes)
    page = data["data"]["products"]["pageInfo"]
    if not page["hasNextPage"]:
        break
    cursor = page["endCursor"]
    time.sleep(0.2)

print(f"  Fetched {len(all_products)} products")

# ── Mutations ─────────────────────────────────────────────────────────────────
UPDATE_PRODUCT = """
mutation updateProduct($input: ProductInput!) {
  productUpdate(input: $input) {
    product { id productType }
    userErrors { field message }
  }
}
"""

UPDATE_VARIANT = """
mutation updateVariant($input: ProductVariantInput!) {
  productVariantUpdate(input: $input) {
    productVariant { id barcode }
    userErrors { field message }
  }
}
"""

# ── Part 1 & 2 & 3 — combined pass ───────────────────────────────────────────
print("\n" + "=" * 60)
print("PART 1: Fill missing barcodes with SKU")
print("=" * 60)

barcode_fixed = 0
barcode_errors = 0

for p in all_products:
    for v in p["variants"]["nodes"]:
        barcode = (v.get("barcode") or "").strip()
        sku     = (v.get("sku") or "").strip()
        if not barcode and sku:
            result = gql(UPDATE_VARIANT, {"input": {"id": v["id"], "barcode": sku}})
            errs = result.get("data", {}).get("productVariantUpdate", {}).get("userErrors", [])
            if errs:
                print(f"  ! {v['id'].split('/')[-1]}: {errs}")
                barcode_errors += 1
            else:
                barcode_fixed += 1
            time.sleep(0.15)

print(f"  Fixed: {barcode_fixed} | Errors: {barcode_errors}")

print("\n" + "=" * 60)
print("PART 2+3: Fix blank product types + standardize taxonomy")
print("=" * 60)

type_fixed_blank   = 0
type_standardized  = 0
type_already_good  = 0
type_errors        = 0

for p in all_products:
    current_type = (p.get("productType") or "").strip()
    pid = p["id"]
    title = p["title"]

    if not current_type:
        # Blank — infer from title
        new_type = infer_product_type(title)
        label = f"BLANK→inferred"
    elif current_type in TAXONOMY_MAP:
        new_type = TAXONOMY_MAP[current_type]
        label = f"'{current_type}'→standardized"
    elif current_type in TAXONOMY_MAP.values():
        # Already a full taxonomy string
        type_already_good += 1
        continue
    else:
        # Unknown type not in map — try case-insensitive match
        match = next((v for k, v in TAXONOMY_MAP.items() if k.lower() == current_type.lower()), None)
        if match:
            new_type = match
            label = f"'{current_type}'→standardized"
        else:
            # Can't map — try keyword inference anyway
            inferred = infer_product_type(title)
            new_type = inferred
            label = f"'{current_type}'→keyword-inferred"

    result = gql(UPDATE_PRODUCT, {"input": {"id": pid, "productType": new_type}})
    errs = result.get("data", {}).get("productUpdate", {}).get("userErrors", [])
    if errs:
        print(f"  ! {title[:50]}: {errs}")
        type_errors += 1
    else:
        if not current_type:
            type_fixed_blank += 1
        else:
            type_standardized += 1
        print(f"  ✓ [{label}] {title[:60]}")
    time.sleep(0.2)

print(f"\n  Blank types fixed:    {type_fixed_blank}")
print(f"  Types standardized:  {type_standardized}")
print(f"  Already correct:     {type_already_good}")
print(f"  Errors:              {type_errors}")

print("\n" + "=" * 60)
print("COMPLETE")
print(f"  Barcodes filled:     {barcode_fixed}")
print(f"  Product types fixed: {type_fixed_blank + type_standardized}")
print("=" * 60)
