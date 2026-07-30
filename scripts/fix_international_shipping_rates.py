#!/usr/bin/env python3
"""
fix_international_shipping_rates.py

Fixes the international shipping zone rates on the General delivery profile:
  BEFORE (broken):
    - "Free Shipping"    $0.00  (all orders, all countries — causes unprofitable/cancelled orders)
    - "Express Shipping" $10.00 (all orders — too cheap for real international shipping)

  AFTER (corrected for POD fulfillment via Printful/Gelato):
    - "Standard International"  $14.99  (orders < $100)
    - "Express International"   $29.99  (all orders)
    - "Free Shipping"            $0.00  (orders >= $100)

The script:
  1. Fetches current method definition IDs from each international zone
  2. Deletes the broken free-shipping and express rates
  3. Adds the corrected three-tier rates

Applies to all 3 location groups (Printful LG1, PODpluser LG2, duvre LG3).
DRY_RUN=true to preview changes without writing.

Usage:
  SHOPIFY_ADMIN_TOKEN=... python scripts/fix_international_shipping_rates.py
  DRY_RUN=true SHOPIFY_ADMIN_TOKEN=... python scripts/fix_international_shipping_rates.py
"""
import os
import sys
import json
import requests

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
SHOP = "lngndny.myshopify.com"
API_VERSION = "2026-04"

# ── Auth — use SHOPIFY_ADMIN_TOKEN (private app token with write_shipping scope)
TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
GQL_URL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}


def gql(query, variables=None):
    r = requests.post(GQL_URL, headers=HEADERS, json={"query": query, "variables": variables or {}})
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        print(f"  [GQL errors] {json.dumps(data['errors'], indent=2)}")
    return data


# ── Known GIDs ────────────────────────────────────────────────────────────────
GENERAL_PROFILE_ID = "gid://shopify/DeliveryProfile/67801841817"

# Location groups
LG1_ID = "gid://shopify/DeliveryLocationGroup/97241792665"   # Printful
LG2_ID = "gid://shopify/DeliveryLocationGroup/97241825433"   # PODpluser
LG3_ID = "gid://shopify/DeliveryLocationGroup/97869267097"   # duvre

# International zone IDs per LG (200+ country zone)
INTL_ZONES = {
    LG1_ID: "gid://shopify/DeliveryZone/465268310169",
    LG2_ID: "gid://shopify/DeliveryZone/465268375705",
    LG3_ID: "gid://shopify/DeliveryZone/467489030297",
}

# ── Step 1: Fetch current method definitions ──────────────────────────────────
FETCH_PROFILE_QUERY = """
query getProfile($id: ID!) {
  deliveryProfile(id: $id) {
    id
    name
    profileLocationGroups {
      locationGroup { id }
      locationGroupZones(first: 20) {
        nodes {
          zone { id name }
          methodDefinitions(first: 20) {
            nodes {
              id
              name
              active
              rateProvider {
                ... on DeliveryRateDefinition {
                  price { amount currencyCode }
                }
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
print("International Shipping Rate Fix — General Delivery Profile")
if DRY_RUN:
    print("  *** DRY RUN MODE — no changes will be written ***")
print("=" * 70)

profile_data = gql(FETCH_PROFILE_QUERY, {"id": GENERAL_PROFILE_ID})
profile = profile_data.get("data", {}).get("deliveryProfile", {})

if not profile:
    print("✗ Could not fetch delivery profile. Check GQL errors above.")
    sys.exit(1)

print(f"\n✓ Fetched profile: {profile['name']}")

# Collect method definition IDs to delete per international zone
methods_to_delete = {}   # zone_gid → [method_def_id, ...]

for plg in profile.get("profileLocationGroups", []):
    lg_id = plg["locationGroup"]["id"]
    intl_zone_id = INTL_ZONES.get(lg_id)
    if not intl_zone_id:
        continue

    for node in plg["locationGroupZones"]["nodes"]:
        zone_id = node["zone"]["id"]
        zone_name = node["zone"]["name"]
        if zone_id != intl_zone_id:
            continue

        print(f"\n  Zone: {zone_name} (LG: {lg_id.split('/')[-1]})")
        to_delete = []
        for method in node["methodDefinitions"]["nodes"]:
            price_info = method.get("rateProvider", {}).get("price", {})
            price = float(price_info.get("amount", 0))
            print(f"    Found method: {method['name']!r}  ${price:.2f}  (id: {method['id'].split('/')[-1]})")
            # Delete "Free Shipping" ($0 flat) and "Express Shipping" ($10) from intl zone
            # We'll recreate free shipping with a $100 minimum threshold
            if method["name"] in ("Free Shipping", "Express Shipping", "Standard International Shipping"):
                to_delete.append(method["id"])
                print(f"      → Marked for deletion")

        if to_delete:
            methods_to_delete[zone_id] = to_delete

if not methods_to_delete:
    print("\n⚠  No methods found to deactivate in international zones.")
    print("   The zone may already be correctly configured, or zone IDs may have changed.")
    print("   Run audit_delivery_profiles.py to inspect current state.")
    sys.exit(0)

total_to_delete = sum(len(v) for v in methods_to_delete.values())
print(f"\n  {total_to_delete} method definition(s) across {len(methods_to_delete)} zone(s) will be deactivated.")

# ── New rate definitions ──────────────────────────────────────────────────────
# $14.99 standard for orders < $100
INTL_STANDARD_METHOD = {
    "name": "Standard International",
    "active": True,
    "rateDefinition": {"price": {"amount": "14.99", "currencyCode": "USD"}},
    "priceConditionsToCreate": [
        {"operator": "GREATER_THAN_OR_EQUAL_TO", "criteria": {"amount": "0.00",  "currencyCode": "USD"}},
        {"operator": "LESS_THAN_OR_EQUAL_TO",    "criteria": {"amount": "99.99", "currencyCode": "USD"}},
    ],
}

# $29.99 express (no minimum)
INTL_EXPRESS_METHOD = {
    "name": "Express International",
    "active": True,
    "rateDefinition": {"price": {"amount": "29.99", "currencyCode": "USD"}},
}

# Free shipping for orders >= $100
INTL_FREE_METHOD = {
    "name": "Free Shipping",
    "active": True,
    "rateDefinition": {"price": {"amount": "0.00", "currencyCode": "USD"}},
    "priceConditionsToCreate": [
        {"operator": "GREATER_THAN_OR_EQUAL_TO", "criteria": {"amount": "100.00", "currencyCode": "USD"}},
    ],
}

NEW_METHODS = [INTL_STANDARD_METHOD, INTL_EXPRESS_METHOD, INTL_FREE_METHOD]

# ── Step 2: Build update payload ──────────────────────────────────────────────
UPDATE_MUTATION = """
mutation updateProfile($id: ID!, $profile: DeliveryProfileInput!) {
  deliveryProfileUpdate(id: $id, profile: $profile) {
    profile {
      id
      profileLocationGroups {
        locationGroup { id }
        locationGroupZones(first: 20) {
          nodes {
            zone { id name }
            methodDefinitions(first: 20) {
              nodes { id name active rateProvider { ... on DeliveryRateDefinition { price { amount } } } }
            }
          }
        }
      }
    }
    userErrors { field message }
  }
}
"""

lg_updates = []
for lg_id, intl_zone_id in INTL_ZONES.items():
    deactivate_ids = methods_to_delete.get(intl_zone_id, [])
    # Shopify has no methodDefinitionsToDelete — deactivate old methods instead.
    # Inactive methods are hidden from customers but can be cleaned up manually via admin.
    zone_update = {
        "id": intl_zone_id,
        "methodDefinitionsToCreate": NEW_METHODS,
        "methodDefinitionsToUpdate": [{"id": mid, "active": False} for mid in deactivate_ids],
    }

    lg_updates.append({
        "id": lg_id,
        "zonesToUpdate": [zone_update],
    })

profile_input = {"locationGroupsToUpdate": lg_updates}

if DRY_RUN:
    print("\n[DRY RUN] Would apply the following update:")
    print(json.dumps(profile_input, indent=2))
    print("\n[DRY RUN] No changes written.")
    sys.exit(0)

# ── Step 3: Apply ─────────────────────────────────────────────────────────────
print("\nApplying update to Shopify...")
result = gql(UPDATE_MUTATION, {"id": GENERAL_PROFILE_ID, "profile": profile_input})

user_errors = result.get("data", {}).get("deliveryProfileUpdate", {}).get("userErrors", [])
if user_errors:
    print("✗ userErrors:")
    for e in user_errors:
        print(f"  - {e.get('field', '?')}: {e['message']}")
    sys.exit(1)

updated_profile = result.get("data", {}).get("deliveryProfileUpdate", {}).get("profile", {})
if not updated_profile:
    print("✗ No profile returned — check GQL errors above")
    print(json.dumps(result, indent=2))
    sys.exit(1)

print("\n✓ Profile updated. New international zone rates:")
for plg in updated_profile.get("profileLocationGroups", []):
    lg_id = plg["locationGroup"]["id"]
    intl_zone_id = INTL_ZONES.get(lg_id)
    for node in plg["locationGroupZones"]["nodes"]:
        if node["zone"]["id"] != intl_zone_id:
            continue
        print(f"\n  LG {lg_id.split('/')[-1]} — {node['zone']['name']}:")
        for m in node["methodDefinitions"]["nodes"]:
            price = m.get("rateProvider", {}).get("price", {}).get("amount", "?")
            status = "✓ active" if m["active"] else "○ inactive"
            print(f"    {status}  {m['name']!r}  ${price}")

print("\n" + "=" * 70)
print("DONE — international shipping rates corrected")
print("Next step: run sync_gmc_shipping.py to push these rates to GMC")
print("=" * 70)
