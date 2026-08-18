#!/usr/bin/env python3
"""
add_paid_shipping_tiers.py
Adds paid shipping tiers to the General delivery profile using the correct
deliveryProfileUpdate → locationGroupsToUpdate → zonesToCreate approach.

Shipping strategy (profit-optimized):
  US Domestic (all 3 LGs):
    - Standard Shipping: $5.99 (orders $0–$99.99)
    - Free Shipping: $0.00 (orders $100+) ← already exists, untouched

  International 12-market (LG1 + LG2):
    - Standard International Shipping: $14.99 (orders $0–$149.99)
    - Free Shipping: $0.00 (orders $150+) ← already exists, untouched

  International 236-country (LG3 only):
    - Standard International Shipping: $24.99 flat
    - Free Shipping: $0.00 ← already exists, untouched

Approach: create NEW zones alongside existing ones inside each LG.
Existing free shipping zones are never touched.
"""
import os, sys, requests, time, json

ADMIN_TOKEN   = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID     = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOP          = "lngndny.myshopify.com"
API_VERSION   = "2026-04"

# ── Auth ──────────────────────────────────────────────────────────────────────
if ADMIN_TOKEN:
    TOKEN = ADMIN_TOKEN
else:
    token_resp = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        data={
            "grant_type":    "client_credentials",
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
    )
    token_resp.raise_for_status()
    TOKEN   = token_resp.json()["access_token"]
GQL_URL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

def gql(query, variables=None):
    r = requests.post(GQL_URL, headers=HEADERS, json={"query": query, "variables": variables or {}})
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        print(f"  [GQL top-level errors] {json.dumps(data['errors'], indent=2)}")
    return data

# ── IDs ───────────────────────────────────────────────────────────────────────
GENERAL_PROFILE_ID = "gid://shopify/DeliveryProfile/67801841817"

# Location group IDs
LG1_ID = "gid://shopify/DeliveryLocationGroup/97241792665"   # Printful
LG2_ID = "gid://shopify/DeliveryLocationGroup/97241825433"   # PODpluser
LG3_ID = "gid://shopify/DeliveryLocationGroup/97869267097"   # duvre

# ── Mutation ──────────────────────────────────────────────────────────────────
UPDATE_PROFILE = """
mutation updateProfile($id: ID!, $profile: DeliveryProfileInput!) {
  deliveryProfileUpdate(id: $id, profile: $profile) {
    profile {
      id
      name
      profileLocationGroups {
        locationGroup { id }
        locationGroupZones(first: 20) {
          nodes {
            zone { id name }
            methodDefinitions(first: 10) {
              nodes { id name active }
            }
          }
        }
      }
    }
    userErrors { field message }
  }
}
"""

# ── Zone IDs from audit (existing zones to ADD rates to) ─────────────────────
# Update existing zones by ID — adding paid method alongside the free one.
# Same country region cannot exist in two zones; we must use the existing zone.

# LG1 (Printful)
LG1_DOM_ZONE_ID  = "gid://shopify/DeliveryZone/465268277401"   # US Domestic
LG1_INTL_ZONE_ID = "gid://shopify/DeliveryZone/465268310169"   # Intl 12

# LG2 (PODpluser)
LG2_DOM_ZONE_ID  = "gid://shopify/DeliveryZone/465268342937"   # US Domestic
LG2_INTL_ZONE_ID = "gid://shopify/DeliveryZone/465268375705"   # Intl 12

# LG3 (duvre)
LG3_DOM_ZONE_ID  = "gid://shopify/DeliveryZone/467488997529"   # US Domestic
LG3_INTL_ZONE_ID = "gid://shopify/DeliveryZone/467489030297"   # Intl 236

# ── Method definition payloads ────────────────────────────────────────────────
US_PAID_METHOD = {
    "name": "Standard Shipping",
    "active": True,
    "rateDefinition": {"price": {"amount": "5.99", "currencyCode": "USD"}},
    "priceConditionsToCreate": [
        {"operator": "GREATER_THAN_OR_EQUAL_TO", "criteria": {"amount": "0.00", "currencyCode": "USD"}},
        {"operator": "LESS_THAN_OR_EQUAL_TO",    "criteria": {"amount": "99.99", "currencyCode": "USD"}},
    ],
}

INTL_12_PAID_METHOD = {
    "name": "Standard International Shipping",
    "active": True,
    "rateDefinition": {"price": {"amount": "14.99", "currencyCode": "USD"}},
    "priceConditionsToCreate": [
        {"operator": "GREATER_THAN_OR_EQUAL_TO", "criteria": {"amount": "0.00",   "currencyCode": "USD"}},
        {"operator": "LESS_THAN_OR_EQUAL_TO",    "criteria": {"amount": "149.99", "currencyCode": "USD"}},
    ],
}

INTL_236_PAID_METHOD = {
    "name": "Standard International Shipping",
    "active": True,
    "rateDefinition": {"price": {"amount": "24.99", "currencyCode": "USD"}},
    # No price conditions — flat rate
}

# ── Build update payload ──────────────────────────────────────────────────────
# Update existing zones (by zone ID) to add paid methods alongside free ones.
# zonesToUpdate uses the same DeliveryLocationGroupZoneInput with id= to target existing zones.
profile_input = {
    "locationGroupsToUpdate": [
        {
            "id": LG1_ID,
            "zonesToUpdate": [
                {"id": LG1_DOM_ZONE_ID,  "methodDefinitionsToCreate": [US_PAID_METHOD]},
                {"id": LG1_INTL_ZONE_ID, "methodDefinitionsToCreate": [INTL_12_PAID_METHOD]},
            ],
        },
        {
            "id": LG2_ID,
            "zonesToUpdate": [
                {"id": LG2_DOM_ZONE_ID,  "methodDefinitionsToCreate": [US_PAID_METHOD]},
                {"id": LG2_INTL_ZONE_ID, "methodDefinitionsToCreate": [INTL_12_PAID_METHOD]},
            ],
        },
        {
            "id": LG3_ID,
            "zonesToUpdate": [
                {"id": LG3_DOM_ZONE_ID,  "methodDefinitionsToCreate": [US_PAID_METHOD]},
                {"id": LG3_INTL_ZONE_ID, "methodDefinitionsToCreate": [INTL_236_PAID_METHOD]},
            ],
        },
    ]
}

print("=" * 70)
print("Adding paid shipping tiers via deliveryProfileUpdate → zonesToCreate")
print("=" * 70)
print(f"\nProfile:  {GENERAL_PROFILE_ID}")
print(f"Strategy:")
print(f"  LG1 (Printful)  + LG2 (PODpluser): US $5.99 + Intl-12 $14.99")
print(f"  LG3 (duvre):                        US $5.99 + Intl-236 $24.99 flat")
print()

result = gql(UPDATE_PROFILE, {"id": GENERAL_PROFILE_ID, "profile": profile_input})

user_errors = result.get("data", {}).get("deliveryProfileUpdate", {}).get("userErrors", [])
if user_errors:
    print("✗ userErrors:")
    for e in user_errors:
        print(f"  - {e['field']}: {e['message']}")
    sys.exit(1)

profile = result.get("data", {}).get("deliveryProfileUpdate", {}).get("profile", {})
if not profile:
    print("✗ No profile returned — check GQL errors above")
    print(json.dumps(result, indent=2))
    sys.exit(1)

print("✓ Profile updated successfully\n")
print("Updated zones per location group:")
for plg in profile.get("profileLocationGroups", []):
    lg_id = plg["locationGroup"]["id"].split("/")[-1]
    print(f"\n  LG {lg_id}:")
    for node in plg["locationGroupZones"]["nodes"]:
        zone_name = node["zone"]["name"]
        zone_id   = node["zone"]["id"].split("/")[-1]
        methods   = [m["name"] for m in node["methodDefinitions"]["nodes"]]
        print(f"    Zone [{zone_id}] {zone_name!r}: {methods}")

print("\n" + "=" * 70)
print("DONE — paid shipping tiers added to General profile")
print("=" * 70)
