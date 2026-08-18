#!/usr/bin/env python3
"""
fix_shipping_rates.py
1. Adds paid shipping tiers to all General profile zones (US + Intl)
2. Deletes all orphaned Gelato delivery profiles

Shipping strategy (profit-optimized):
  US Domestic:
    - Standard Shipping: $5.99 (orders under $100)
    - Free Shipping:     $0.00 (orders $100+)   ← already exists, keep it
  International (12 markets):
    - Standard Intl Shipping: $14.99 (orders under $150)
    - Free Shipping:          $0.00  (orders $150+) ← already exists, keep it
  International (236 countries):
    - Standard Intl Shipping: $24.99 flat ← add this, free stays
"""
import os, requests, time

ADMIN_TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOP = "lngndny.myshopify.com"
API_VERSION = "2026-04"

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
GQL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

def gql(query, variables=None):
    r = requests.post(GQL, headers=HEADERS, json={"query": query, "variables": variables or {}})
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        print(f"  GQL errors: {data['errors']}")
    return data

# ── Zone IDs from audit ───────────────────────────────────────
# 3 location groups × (Domestic + International) = 6 zones
DOMESTIC_ZONES = [
    "gid://shopify/DeliveryZone/465268277401",   # LG1 Domestic (Printful)
    "gid://shopify/DeliveryZone/465268342937",   # LG2 Domestic (PODpluser)
    "gid://shopify/DeliveryZone/467488997529",   # LG3 Domestic (duvre)
]
INTL_12_ZONES = [
    "gid://shopify/DeliveryZone/465268310169",   # LG1 Intl 12
    "gid://shopify/DeliveryZone/465268375705",   # LG2 Intl 12
]
INTL_236_ZONES = [
    "gid://shopify/DeliveryZone/467489030297",   # LG3 Intl 236
]

# GraphQL mutation to add a method definition (rate) to a zone
ADD_RATE = """
mutation addRate($zoneId: ID!, $methodInput: DeliveryMethodDefinitionInput!) {
  deliveryMethodDefinitionCreate(methodDefinition: $methodInput, zoneId: $zoneId) {
    methodDefinition { id name }
    userErrors { field message }
  }
}
"""

def add_flat_rate(zone_id, name, amount_cents_str, min_subtotal=None, max_subtotal=None):
    """Add a flat rate to a zone with optional order subtotal conditions."""
    conditions = []
    if min_subtotal is not None:
        conditions.append({
            "field": "TOTAL_PRICE",
            "operator": "GREATER_THAN_OR_EQUAL_TO",
            "criteria": {"type": "PRICE", "value": str(min_subtotal)}
        })
    if max_subtotal is not None:
        conditions.append({
            "field": "TOTAL_PRICE",
            "operator": "LESS_THAN_OR_EQUAL_TO",
            "criteria": {"type": "PRICE", "value": str(max_subtotal)}
        })

    method_input = {
        "name": name,
        "active": True,
        "rateDefinition": {
            "price": {"amount": amount_cents_str, "currencyCode": "USD"}
        },
        "methodConditions": conditions
    }
    result = gql(ADD_RATE, {"zoneId": zone_id, "methodInput": method_input})
    errs = result.get("data", {}).get("deliveryMethodDefinitionCreate", {}).get("userErrors", [])
    if errs:
        print(f"    ! Error: {errs}")
    else:
        mid = result.get("data", {}).get("deliveryMethodDefinitionCreate", {}).get("methodDefinition", {}).get("id")
        print(f"    + Added '{name}' ${amount_cents_str} → {zone_id.split('/')[-1]}")
    time.sleep(0.4)

# ── Part 1: Add paid tiers ────────────────────────────────────
print("=" * 60)
print("PART 1: Adding paid shipping tiers")
print("=" * 60)

print("\n[US Domestic zones] — $5.99 under $100, free $100+ already exists")
for zid in DOMESTIC_ZONES:
    add_flat_rate(zid, "Standard Shipping", "5.99", min_subtotal="0.00", max_subtotal="99.99")

print("\n[International 12 zones] — $14.99 under $150, free $150+ already exists")
for zid in INTL_12_ZONES:
    add_flat_rate(zid, "Standard International Shipping", "14.99", min_subtotal="0.00", max_subtotal="149.99")

print("\n[International 236 zone] — $24.99 flat (free already exists)")
for zid in INTL_236_ZONES:
    add_flat_rate(zid, "Standard International Shipping", "24.99")

# ── Part 2: Delete Gelato profiles ───────────────────────────
print("\n" + "=" * 60)
print("PART 2: Deleting orphaned Gelato profiles")
print("=" * 60)

GELATO_IDS = [
    "gid://shopify/DeliveryProfile/96535871641",  # Small Posters
    "gid://shopify/DeliveryProfile/96535904409",  # Large Posters
    "gid://shopify/DeliveryProfile/96535937177",  # Small Framed Posters
    "gid://shopify/DeliveryProfile/96535969945",  # Medium Framed Posters
    "gid://shopify/DeliveryProfile/96536002713",  # Large Framed Posters
    "gid://shopify/DeliveryProfile/96536035481",  # Small Canvas
    "gid://shopify/DeliveryProfile/96536068249",  # Medium Canvas
    "gid://shopify/DeliveryProfile/96536101017",  # Large Canvas
    "gid://shopify/DeliveryProfile/96536133785",  # Small Framed Canvas
    "gid://shopify/DeliveryProfile/96536166553",  # Medium Framed Canvas
    "gid://shopify/DeliveryProfile/96536199321",  # Large Framed Canvas
    "gid://shopify/DeliveryProfile/96536232089",  # Small Acrylic
    "gid://shopify/DeliveryProfile/96536264857",  # Medium Acrylic
    "gid://shopify/DeliveryProfile/96536297625",  # Large Acrylic
    "gid://shopify/DeliveryProfile/96536330393",  # Mugs
    "gid://shopify/DeliveryProfile/96536363161",  # Mugs 11oz white
    "gid://shopify/DeliveryProfile/96536395929",  # Mugs 11oz colored
    "gid://shopify/DeliveryProfile/96536428697",  # T-Shirts
    "gid://shopify/DeliveryProfile/96536461465",  # Hoodies Sweatshirts
    "gid://shopify/DeliveryProfile/96536494233",  # Tote Bags
    "gid://shopify/DeliveryProfile/96536527001",  # Baby Clothing
    "gid://shopify/DeliveryProfile/96536559769",  # Small Medium Wall Hangers
    "gid://shopify/DeliveryProfile/96536592537",  # Large Wall Hangers
    "gid://shopify/DeliveryProfile/96536625305",  # Cards
    "gid://shopify/DeliveryProfile/96536658073",  # Small Foam Prints
    "gid://shopify/DeliveryProfile/96536690841",  # Medium Foam Prints
    "gid://shopify/DeliveryProfile/96536723609",  # Large Foam Prints
    "gid://shopify/DeliveryProfile/96536756377",  # Hardcover Photo Books
]

DELETE = """
mutation($id: ID!) {
  deliveryProfileRemove(id: $id) {
    job { id done }
    userErrors { field message }
  }
}
"""

deleted = 0
errors = 0
for gid in GELATO_IDS:
    result = gql(DELETE, {"id": gid})
    errs = result.get("data", {}).get("deliveryProfileRemove", {}).get("userErrors", [])
    name = gid.split("/")[-1]
    if errs:
        print(f"  ! Error deleting {name}: {errs}")
        errors += 1
    else:
        print(f"  ✓ Deleted profile {name}")
        deleted += 1
    time.sleep(0.4)

# Also get remaining profiles to find any we missed
LIST = """
query {
  deliveryProfiles(first: 50) {
    nodes { id name default profileItems(first:1) { nodes { id } } }
  }
}
"""
remaining = gql(LIST)
remaining_gelato = [
    p for p in remaining["data"]["deliveryProfiles"]["nodes"]
    if "gelato" in p["name"].lower() and not p.get("default")
       and len(p.get("profileItems", {}).get("nodes", [])) == 0
]
for p in remaining_gelato:
    result = gql(DELETE, {"id": p["id"]})
    errs = result.get("data", {}).get("deliveryProfileRemove", {}).get("userErrors", [])
    if errs:
        print(f"  ! Error deleting '{p['name']}': {errs}")
        errors += 1
    else:
        print(f"  ✓ Deleted '{p['name']}'")
        deleted += 1
    time.sleep(0.4)

print(f"\n{'='*60}")
print(f"COMPLETE")
print(f"  Rates added: 6 zones updated")
print(f"  Profiles deleted: {deleted} | Errors: {errors}")
