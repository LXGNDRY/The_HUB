#!/usr/bin/env python3
"""
fix_shopify_country_hs.py

Audits every Shopify product variant for missing countryCodeOfOrigin and
harmonizedSystemCode, then fills in defaults derived from each product's type.

Default country of origin: CN (China) — override via env var COUNTRY_OF_ORIGIN.
HS codes are mapped per product-type taxonomy string (6-digit, no separator).

Set DRY_RUN=true to preview changes without writing to Shopify.
"""

import os
import sys
import time
import requests

CLIENT_ID     = os.environ["SHOPIFY_CLIENT_ID"]
CLIENT_SECRET = os.environ["SHOPIFY_CLIENT_SECRET"]
SHOP          = os.getenv("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
API_VERSION   = "2026-04"
DRY_RUN       = os.getenv("DRY_RUN", "false").lower() == "true"

# Default country of origin (ISO 3166-1 alpha-2) — override via env var
DEFAULT_COUNTRY = os.getenv("COUNTRY_OF_ORIGIN", "CN")

token_resp = requests.post(
    f"https://{SHOP}/admin/oauth/access_token",
    data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
    timeout=15,
)
token_resp.raise_for_status()
TOKEN   = token_resp.json()["access_token"]
GQL_URL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}


def gql(query, variables=None):
    r = requests.post(GQL_URL, headers=HEADERS, json={"query": query, "variables": variables or {}}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        print(f"  [GQL error] {data['errors']}", file=sys.stderr)
    return data


# ── HS code map keyed on product-type taxonomy strings ───────────────────────
# 6-digit harmonized system codes (no separator).
# All codes assume primary cotton composition — most common for branded apparel.
HS_CODE_MAP = {
    # Shirts / Tops / Tees / Tanks
    "Apparel & Accessories > Clothing > Shirts & Tops":      "610910",  # cotton knit T-shirts/vests
    # Hoodies / Sweatshirts / Fleece
    "Apparel & Accessories > Clothing > Activewear > Hoodies": "611020",  # cotton jerseys/sweatshirts
    # Pants / Sweatpants / Joggers / Jeans
    "Apparel & Accessories > Clothing > Pants":              "610342",  # cotton knit trousers/tracksuit bottoms
    # Shorts
    "Apparel & Accessories > Clothing > Shorts":             "610342",  # cotton knit shorts
    # Hats / Caps / Beanies
    "Apparel & Accessories > Clothing Accessories > Hats":   "650500",  # hats and headgear
    # Sunglasses / Shades
    "Apparel & Accessories > Clothing Accessories > Sunglasses": "900410",  # sunglasses
    # Outerwear / Jackets / Windbreakers / Bombers
    "Apparel & Accessories > Clothing > Outerwear":          "610120",  # cotton knit jackets/blazers
    # Sets / Tracksuits / Lounge Sets / Outfit Sets
    "Apparel & Accessories > Clothing > Outfit Sets":        "621133",  # track suits of man-made fibers
    # Polo shirts
    "Apparel & Accessories > Clothing > Polo":               "610510",  # cotton knit polo shirts
}

# Fallback keyword-based HS code inference for unrecognised product types
def infer_hs_code(product_type: str, title: str) -> str:
    t = (product_type + " " + title).lower()
    if any(k in t for k in ["hoodie", "sweatshirt", "hooded", "fleece", "crewneck"]):
        return "611020"
    if any(k in t for k in ["pant", "jogger", "trackpant", "sweatpant", "jean", "denim"]):
        return "610342"
    if "short" in t:
        return "610342"
    if any(k in t for k in ["hat", "cap", "beanie", "snapback", "trucker"]):
        return "650500"
    if any(k in t for k in ["sunglass", "shade"]):
        return "900410"
    if any(k in t for k in ["jacket", "windbreaker", "bomber", "outerwear"]):
        return "610120"
    if any(k in t for k in ["set", "tracksuit", "outfit", "lounge"]):
        return "621133"
    if "polo" in t:
        return "610510"
    # Default: cotton knit T-shirt category covers most branded tops
    return "610910"


# ── GraphQL queries ───────────────────────────────────────────────────────────
FETCH_PRODUCTS = """
query($cursor: String) {
  products(first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      title
      productType
      variants(first: 100) {
        nodes {
          id
          sku
          title
          inventoryItem {
            id
            countryCodeOfOrigin
            harmonizedSystemCode
          }
        }
      }
    }
  }
}
"""

# countryCodeOfOrigin and harmonizedSystemCode live on InventoryItem, not ProductVariant.
# Use inventoryItemUpdate once per variant.
UPDATE_INVENTORY_ITEM = """
mutation inventoryItemUpdate($id: ID!, $input: InventoryItemUpdateInput!) {
  inventoryItemUpdate(id: $id, input: $input) {
    inventoryItem {
      id
      countryCodeOfOrigin
      harmonizedSystemCode
    }
    userErrors { field message }
  }
}
"""


# ── Fetch all products ────────────────────────────────────────────────────────
print("=" * 65)
print(f"Shopify Country of Origin + HS Code Fixer")
print(f"  Shop:         {SHOP}")
print(f"  Default COO:  {DEFAULT_COUNTRY}")
print(f"  DRY RUN:      {DRY_RUN}")
print("=" * 65)
print("\nFetching all products...")

all_products = []
cursor = None
while True:
    data = gql(FETCH_PRODUCTS, {"cursor": cursor})
    nodes = data["data"]["products"]["nodes"]
    all_products.extend(nodes)
    page = data["data"]["products"]["pageInfo"]
    if not page["hasNextPage"]:
        break
    cursor = page["endCursor"]
    time.sleep(0.2)

print(f"  Fetched {len(all_products)} products\n")


# ── Audit and collect changes ─────────────────────────────────────────────────
print("=" * 65)
print("AUDIT — variants missing country of origin or HS code")
print("=" * 65)

# { product_id: { title, variants_to_update: [{id, coo, hs}] } }
updates: dict = {}

total_variants      = 0
missing_coo         = 0
missing_hs          = 0
already_complete    = 0

for p in all_products:
    pid        = p["id"]
    ptitle     = p["title"]
    ptype      = (p.get("productType") or "").strip()
    hs_default = HS_CODE_MAP.get(ptype) or infer_hs_code(ptype, ptitle)

    variant_updates = []

    for v in p["variants"]["nodes"]:
        total_variants += 1
        vtitle  = v.get("title", "")
        inv     = v.get("inventoryItem") or {}
        inv_id  = inv.get("id", "")
        coo     = (inv.get("countryCodeOfOrigin") or "").strip()
        hs      = (inv.get("harmonizedSystemCode") or "").strip()

        needs_coo = not coo
        needs_hs  = not hs

        if not needs_coo and not needs_hs:
            already_complete += 1
            continue

        if needs_coo:
            missing_coo += 1
        if needs_hs:
            missing_hs += 1

        new_coo = coo if coo else DEFAULT_COUNTRY
        new_hs  = hs if hs else hs_default

        print(
            f"  {'[DRY]' if DRY_RUN else '     '} {ptitle[:45]:<45} | {vtitle:<12} "
            f"| COO: {coo or '—':>3} → {new_coo}  |  HS: {hs or '——————':>6} → {new_hs}"
        )
        variant_updates.append({"inv_id": inv_id, "countryCodeOfOrigin": new_coo, "harmonizedSystemCode": new_hs})

    if variant_updates:
        updates[pid] = {"title": ptitle, "variants": variant_updates}

print(f"\n  Total variants:        {total_variants}")
print(f"  Already complete:      {already_complete}")
print(f"  Missing COO:           {missing_coo}")
print(f"  Missing HS code:       {missing_hs}")
print(f"  Products needing fix:  {len(updates)}")

if not updates:
    print("\nAll variants already have country of origin and HS code set. Nothing to do.")
    sys.exit(0)

if DRY_RUN:
    print("\n[DRY RUN] No changes written to Shopify.")
    sys.exit(0)

# ── Apply changes ─────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("APPLYING CHANGES")
print("=" * 65)

fixed      = 0
errored    = 0

for pid, info in updates.items():
    product_errors = 0
    for v in info["variants"]:
        result = gql(UPDATE_INVENTORY_ITEM, {
            "id": v["inv_id"],
            "input": {
                "countryCodeOfOrigin": v["countryCodeOfOrigin"],
                "harmonizedSystemCode": v["harmonizedSystemCode"],
            },
        })
        errs = result.get("data", {}).get("inventoryItemUpdate", {}).get("userErrors", [])
        if errs:
            print(f"  ! {info['title'][:55]} [{v['inv_id'].split('/')[-1]}]: {errs}")
            product_errors += 1
            errored += 1
        else:
            fixed += 1
        time.sleep(0.2)
    if product_errors == 0:
        count = len(info["variants"])
        print(f"  ✓ {info['title'][:60]} ({count} variant{'s' if count != 1 else ''})")

print("\n" + "=" * 65)
print("COMPLETE")
print(f"  Variants updated:  {fixed}")
print(f"  Products errored:  {errored}")
print("=" * 65)
