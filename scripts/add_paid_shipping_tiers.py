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

CLIENT_ID     = os.environ["SHOPIFY_CLIENT_ID"]
CLIENT_SECRET = os.environ["SHOPIFY_CLIENT_SECRET"]
SHOP          = "lngndny.myshopify.com"
API_VERSION   = "2026-04"

# ── Auth ──────────────────────────────────────────────────────────────────────
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

# ── Zone definitions ──────────────────────────────────────────────────────────
# US domestic paid tier — applies to all 3 LGs
US_PAID_ZONE = {
    "name": "United States — Paid",
    "countries": [{"code": "US", "includeAllProvinces": True}],
    "methodDefinitionsToCreate": [
        {
            "name": "Standard Shipping",
            "active": True,
            "rateDefinition": {
                "price": {"amount": "5.99", "currencyCode": "USD"}
            },
            "priceConditionsToCreate": [
                {
                    "operator": "GREATER_THAN_OR_EQUAL_TO",
                    "criteria": {"amount": "0.00", "currencyCode": "USD"},
                },
                {
                    "operator": "LESS_THAN_OR_EQUAL_TO",
                    "criteria": {"amount": "99.99", "currencyCode": "USD"},
                },
            ],
        }
    ],
}

# International 12-market paid tier — LG1 + LG2 only
# Country codes matching existing "Intl 12" zone scope
INTL_12_COUNTRIES = [
    {"code": "CA", "includeAllProvinces": True},
    {"code": "GB", "includeAllProvinces": True},
    {"code": "AU", "includeAllProvinces": True},
    {"code": "NZ", "includeAllProvinces": True},
    {"code": "IE", "includeAllProvinces": True},
    {"code": "DE", "includeAllProvinces": True},
    {"code": "FR", "includeAllProvinces": True},
    {"code": "NL", "includeAllProvinces": True},
    {"code": "SE", "includeAllProvinces": True},
    {"code": "AT", "includeAllProvinces": True},
    {"code": "JP", "includeAllProvinces": True},
    {"code": "SG", "includeAllProvinces": True},
]

INTL_12_PAID_ZONE = {
    "name": "International 12 — Paid",
    "countries": INTL_12_COUNTRIES,
    "methodDefinitionsToCreate": [
        {
            "name": "Standard International Shipping",
            "active": True,
            "rateDefinition": {
                "price": {"amount": "14.99", "currencyCode": "USD"}
            },
            "priceConditionsToCreate": [
                {
                    "operator": "GREATER_THAN_OR_EQUAL_TO",
                    "criteria": {"amount": "0.00", "currencyCode": "USD"},
                },
                {
                    "operator": "LESS_THAN_OR_EQUAL_TO",
                    "criteria": {"amount": "149.99", "currencyCode": "USD"},
                },
            ],
        }
    ],
}

# International 236-country paid tier — LG3 (duvre) only
# restOfWorld must be set at the DeliveryCountryInput level, not on the zone
INTL_236_PAID_ZONE = {
    "name": "International — Paid",
    "countries": [{"restOfWorld": True}],
    "methodDefinitionsToCreate": [
        {
            "name": "Standard International Shipping",
            "active": True,
            "rateDefinition": {
                "price": {"amount": "24.99", "currencyCode": "USD"}
            },
            # No price condition — flat rate for all orders
        }
    ],
}

# ── Build update payload ──────────────────────────────────────────────────────
# LG1 (Printful): US paid + Intl-12 paid
# LG2 (PODpluser): US paid + Intl-12 paid
# LG3 (duvre): US paid + Intl-236 paid (flat)
profile_input = {
    "locationGroupsToUpdate": [
        {
            "id": LG1_ID,
            "zonesToCreate": [US_PAID_ZONE, INTL_12_PAID_ZONE],
        },
        {
            "id": LG2_ID,
            "zonesToCreate": [US_PAID_ZONE, INTL_12_PAID_ZONE],
        },
        {
            "id": LG3_ID,
            "zonesToCreate": [US_PAID_ZONE, INTL_236_PAID_ZONE],
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
