#!/usr/bin/env python3
"""
fix_shopify_product_data.py

1. Fill missing barcodes with SKU values (464 variants)
2. Fix 29 products with blank product type (inferred from title keywords)
3. Standardize all product types to Google Shopping taxonomy strings
"""
import os, requests, json, time, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.product_compliance import resolve_product_type, _CANONICAL_TYPES

ADMIN_TOKEN   = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID     = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOP          = os.getenv("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
API_VERSION   = "2026-04"

if ADMIN_TOKEN:
    TOKEN = ADMIN_TOKEN
else:
    token_resp = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    )
    TOKEN = token_resp.json()["access_token"]
GQL_URL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

def gql(query, variables=None):
    r = requests.post(GQL_URL, headers=HEADERS, json={"query": query, "variables": variables or {}})
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        print(f"  [GQL error] {data['errors']}")
    return data

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

    if current_type in _CANONICAL_TYPES:
        type_already_good += 1
        continue

    new_type = resolve_product_type(current_type, title)
    label = "BLANK→inferred" if not current_type else f"'{current_type}'→standardized"

    if DRY_RUN:
        print(f"  [DRY RUN] [{label}] {title[:60]}")
        if not current_type:
            type_fixed_blank += 1
        else:
            type_standardized += 1
        continue

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
