#!/usr/bin/env python3
"""
audit_variant_coverage.py

Audits all Shopify product variants for:
  - weight / weightUnit
  - barcode
  - countryCodeOfOrigin  (on inventoryItem)
  - harmonizedSystemCode (on inventoryItem)

Prints a per-product breakdown and a summary table so gaps are easy to spot.
"""

import os
import sys
import time
import requests

ADMIN_TOKEN   = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID     = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOP          = os.getenv("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
API_VERSION   = "2026-04"

if CLIENT_ID and CLIENT_SECRET:
    token_resp = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        json={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
        timeout=15,
    )
    token_resp.raise_for_status()
    TOKEN   = token_resp.json()["access_token"]
elif ADMIN_TOKEN:
    TOKEN = ADMIN_TOKEN
else:
    raise RuntimeError("Set SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET, or SHOPIFY_ADMIN_TOKEN.")
GQL_URL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}


def gql(query, variables=None):
    r = requests.post(GQL_URL, headers=HEADERS, json={"query": query, "variables": variables or {}}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        print(f"  [GQL error] {data['errors']}", file=sys.stderr)
    return data


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
          barcode
          inventoryItem {
            countryCodeOfOrigin
            harmonizedSystemCode
            measurement {
              weight {
                value
                unit
              }
            }
          }
        }
      }
    }
  }
}
"""

print("=" * 70)
print("Shopify Variant Coverage Audit")
print(f"  Shop: {SHOP}")
print("=" * 70)
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

# ── Counters ──────────────────────────────────────────────────────────────────
total      = 0
no_weight  = []
no_barcode = []
no_coo     = []
no_hs      = []

print(f"{'PRODUCT':<50} {'VAR':<12} {'WT':>4} {'BAR':>4} {'COO':>4} {'HS':>4}")
print("-" * 78)

for p in all_products:
    ptitle = p["title"]
    for v in p["variants"]["nodes"]:
        total += 1
        vtitle  = v.get("title", "")
        sku     = v.get("sku") or ""
        barcode = (v.get("barcode") or "").strip()
        inv     = v.get("inventoryItem") or {}
        coo     = (inv.get("countryCodeOfOrigin") or "").strip()
        hs      = (inv.get("harmonizedSystemCode") or "").strip()
        meas    = inv.get("measurement") or {}
        wt      = meas.get("weight") or {}
        weight_val = wt.get("value")

        missing_weight  = weight_val is None or weight_val == 0
        missing_barcode = not barcode
        missing_coo     = not coo
        missing_hs      = not hs

        if missing_weight:
            no_weight.append((ptitle, vtitle, sku))
        if missing_barcode:
            no_barcode.append((ptitle, vtitle, sku))
        if missing_coo:
            no_coo.append((ptitle, vtitle, sku))
        if missing_hs:
            no_hs.append((ptitle, vtitle, sku))

        if missing_weight or missing_barcode or missing_coo or missing_hs:
            wt_flag  = "  --" if missing_weight  else "  ok"
            bar_flag = "  --" if missing_barcode else "  ok"
            coo_flag = "  --" if missing_coo     else "  ok"
            hs_flag  = "  --" if missing_hs      else "  ok"
            label = f"{ptitle[:48]:<50} {vtitle[:10]:<12}"
            print(f"  {label}{wt_flag}{bar_flag}{coo_flag}{hs_flag}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  Total variants:           {total:>5}")
print(f"  Missing weight:           {len(no_weight):>5}  ({100*len(no_weight)//total if total else 0}%)")
print(f"  Missing barcode:          {len(no_barcode):>5}  ({100*len(no_barcode)//total if total else 0}%)")
print(f"  Missing COO:              {len(no_coo):>5}  ({100*len(no_coo)//total if total else 0}%)")
print(f"  Missing HS code:          {len(no_hs):>5}  ({100*len(no_hs)//total if total else 0}%)")

complete = total - len(set(
    (pt, vt, sk) for pt, vt, sk in no_weight + no_barcode + no_coo + no_hs
))
print(f"  Fully complete variants:  {complete:>5}  ({100*complete//total if total else 0}%)")
print("=" * 70)
