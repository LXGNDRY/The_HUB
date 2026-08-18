#!/usr/bin/env python3
"""
audit_delivery_profiles.py
Pulls full structure of all delivery profiles — IDs, zones, existing rates.
"""
import os, requests, json, time

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
    return r.json()

QUERY = """
query($cursor: String) {
  deliveryProfiles(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      name
      default
      profileLocationGroups {
        locationGroup { id locations(first:5) { nodes { id name } } }
        locationGroupZones(first: 20) {
          nodes {
            zone {
              id
              name
              countries { code { countryCode } name }
            }
            methodDefinitions(first: 10) {
              nodes {
                id
                name
                active
                rateProvider {
                  ... on DeliveryRateDefinition {
                    id
                    price { amount currencyCode }
                  }
                }
                methodConditions {
                  id
                  field
                  operator
                  conditionCriteria {
                    ... on MoneyV2 { amount currencyCode }
                    ... on Weight { unit value }
                  }
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

profiles = []
cursor = None
while True:
    data = gql(QUERY, {"cursor": cursor})
    page = data["data"]["deliveryProfiles"]
    profiles.extend(page["nodes"])
    if not page["pageInfo"]["hasNextPage"]:
        break
    cursor = page["pageInfo"]["endCursor"]
    time.sleep(0.3)

for p in profiles:
    if not p.get("default") and "gelato" not in p["name"].lower() and len(p.get("profileLocationGroups", [])) == 0:
        continue
    print(f"\n{'='*60}")
    print(f"PROFILE: {p['name']} (default={p.get('default')}) | ID: {p['id']}")
    for lg in p.get("profileLocationGroups", []):
        locs = [l["name"] for l in lg["locationGroup"]["locations"]["nodes"]]
        lg_id = lg["locationGroup"]["id"]
        print(f"  Location group ID: {lg_id}")
        print(f"  Locations: {', '.join(locs)}")
        for zone_node in lg.get("locationGroupZones", {}).get("nodes", []):
            z = zone_node["zone"]
            countries = [c["name"] for c in z.get("countries", [])]
            print(f"\n    ZONE: {z['name']} | ID: {z['id']}")
            print(f"    Countries ({len(countries)}): {', '.join(countries[:8])}{'...' if len(countries)>8 else ''}")
            methods = zone_node.get("methodDefinitions", {}).get("nodes", [])
            if not methods:
                print(f"    Rates: NONE")
            for m in methods:
                rate = m.get("rateProvider", {})
                price = rate.get("price", {}).get("amount", "?")
                conditions = m.get("methodConditions", [])
                cond_str = ""
                for c in conditions:
                    val = c.get("conditionCriteria", {}).get("amount") or c.get("conditionCriteria", {}).get("value")
                    cond_str += f" [{c['field']} {c['operator']} {val}]"
                print(f"    Rate: {m['name']} — ${price}{cond_str} | method ID: {m['id']}")
