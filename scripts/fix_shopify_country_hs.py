#!/usr/bin/env python3
"""
fix_shopify_country_hs.py

Audits every Shopify product variant for missing countryCodeOfOrigin and
harmonizedSystemCode, then fills in defaults derived from each product's type.

COO logic (same as the webhook handler):
  - Check for a `coo:XX` product tag first (e.g. `coo:US`)
  - Fall back to DEFAULT_COO env var (default: CN)

Set FORCE_OVERWRITE=true to overwrite COO even when already set
(use this to correct a bad previous batch run, e.g. incorrect US stamping).

Set DRY_RUN=true to preview changes without writing to Shopify.
"""

import os
import sys
import time
import requests

# ── Allow running standalone (outside the installed package) ──────────────────
import importlib.util, pathlib
_repo_root = pathlib.Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from modules.product_compliance import HS_CODE_MAP, infer_hs_code, resolve_coo  # noqa: E402

ADMIN_TOKEN     = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID      = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET  = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOP           = os.getenv("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
API_VERSION    = "2026-04"
DRY_RUN        = os.getenv("DRY_RUN", "false").lower() == "true"
FORCE_OVERWRITE = os.getenv("FORCE_OVERWRITE", "false").lower() == "true"

if ADMIN_TOKEN:
    TOKEN = ADMIN_TOKEN
else:
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


# ── GraphQL queries ───────────────────────────────────────────────────────────
FETCH_PRODUCTS = """
query($cursor: String) {
  products(first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      title
      productType
      tags
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
print("Shopify Country of Origin + HS Code Fixer")
print(f"  Shop:            {SHOP}")
print(f"  DRY RUN:         {DRY_RUN}")
print(f"  FORCE_OVERWRITE: {FORCE_OVERWRITE}")
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
print("AUDIT — variants needing COO or HS code update")
print("=" * 65)

updates: dict = {}

total_variants   = 0
needs_update     = 0
already_complete = 0

for p in all_products:
    pid       = p["id"]
    ptitle    = p["title"]
    ptype     = (p.get("productType") or "").strip()
    tags      = p.get("tags") or []
    # GraphQL returns tags as a list; REST webhook returns a comma-string — handle both
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    coo_default = resolve_coo(tags)
    hs_default  = infer_hs_code(ptype, ptitle)
    variant_updates = []

    for v in p["variants"]["nodes"]:
        total_variants += 1
        vtitle  = v.get("title", "")
        inv     = v.get("inventoryItem") or {}
        inv_id  = inv.get("id", "")
        cur_coo = (inv.get("countryCodeOfOrigin") or "").strip()
        cur_hs  = (inv.get("harmonizedSystemCode") or "").strip()

        needs_coo = (not cur_coo) or (FORCE_OVERWRITE and cur_coo != coo_default)
        needs_hs  = not cur_hs

        if not needs_coo and not needs_hs:
            already_complete += 1
            continue

        needs_update += 1
        new_coo = coo_default if needs_coo else cur_coo
        new_hs  = hs_default  if needs_hs  else cur_hs

        flag = "[DRY]" if DRY_RUN else "     "
        coo_arrow = f"{cur_coo or '—':>3} → {new_coo}" if needs_coo else f"{cur_coo} (ok)"
        hs_arrow  = f"{cur_hs or '——————':>6} → {new_hs}" if needs_hs else f"{cur_hs} (ok)"
        print(f"  {flag} {ptitle[:42]:<42} | {vtitle:<10} | COO: {coo_arrow}  HS: {hs_arrow}")

        variant_updates.append({"inv_id": inv_id, "countryCodeOfOrigin": new_coo, "harmonizedSystemCode": new_hs})

    if variant_updates:
        updates[pid] = {"title": ptitle, "variants": variant_updates}

print(f"\n  Total variants:        {total_variants}")
print(f"  Already complete:      {already_complete}")
print(f"  Needing update:        {needs_update}")
print(f"  Products to update:    {len(updates)}")

if not updates:
    print("\nAll variants are up to date. Nothing to do.")
    sys.exit(0)

if DRY_RUN:
    print("\n[DRY RUN] No changes written to Shopify.")
    sys.exit(0)

# ── Apply changes ─────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("APPLYING CHANGES")
print("=" * 65)

fixed   = 0
errored = 0

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
print(f"  Errors:            {errored}")
print("=" * 65)
