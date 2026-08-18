#!/usr/bin/env python3
"""Introspect DeliveryLocationGroupZoneInput and DeliveryCountryInput to find valid fields."""
import os, requests, json

ADMIN_TOKEN   = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID     = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOP          = "lngndny.myshopify.com"
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

def introspect(type_name):
    q = f"""
    {{
      __type(name: "{type_name}") {{
        name
        inputFields {{
          name
          description
          type {{ name kind ofType {{ name kind }} }}
        }}
      }}
    }}
    """
    r = requests.post(GQL_URL, headers=HEADERS, json={"query": q})
    return r.json()

for t in ["DeliveryLocationGroupZoneInput", "DeliveryCountryInput", "DeliveryMethodDefinitionInput"]:
    data = introspect(t)
    print(f"\n{'='*60}")
    print(f"Type: {t}")
    print('='*60)
    fields = data.get("data", {}).get("__type", {}).get("inputFields", [])
    for f in fields:
        type_info = f["type"]
        type_name = type_info.get("name") or (type_info.get("ofType") or {}).get("name", "")
        print(f"  {f['name']}: {type_name}")
        if f.get("description"):
            print(f"    → {f['description']}")

for t2 in ["DeliveryLocationGroupInput", "DeliveryProfileInput"]:
    data = introspect(t2)
    print(f"\n{'='*60}")
    print(f"Type: {t2}")
    print('='*60)
    fields = data.get("data", {}).get("__type", {}).get("inputFields", [])
    for f in fields:
        type_info = f["type"]
        type_name = type_info.get("name") or (type_info.get("ofType") or {}).get("name", "")
        print(f"  {f['name']}: {type_name}")
        if f.get("description"):
            print(f"    → {f['description']}")
