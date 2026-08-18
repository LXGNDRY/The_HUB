#!/usr/bin/env python3
import os, requests, json

ADMIN_TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOP = "lngndny.myshopify.com"
API_VERSION = "2026-04"

if ADMIN_TOKEN:
    TOKEN = ADMIN_TOKEN
else:
    token_resp = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    )
    TOKEN = token_resp.json()["access_token"]
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"

# Check delivery profiles (modern Shopify shipping architecture)
r = requests.get(f"{BASE}/shipping_zones.json", headers=HEADERS)
zones = r.json().get("shipping_zones", [])
zone = zones[0]
zid = zone["id"]
print(f"Testing zone ID: {zid} ({zone['name']})")

# Try with verbose error
body = {"price_based_shipping_rate": {"name": "Test Rate", "price": "5.99"}}
r2 = requests.post(
    f"{BASE}/shipping_zones/{zid}/price_based_shipping_rates.json",
    headers=HEADERS, json=body
)
print(f"Status: {r2.status_code}")
print(f"Response: {r2.text[:500]}")
print(f"Headers: {dict(r2.headers)}")

# Also check if there are delivery profiles (newer API)
r3 = requests.get(f"{BASE}/delivery_profiles.json", headers=HEADERS)
print(f"\nDelivery profiles status: {r3.status_code}")
if r3.status_code == 200:
    profiles = r3.json().get("delivery_profiles", [])
    print(f"Delivery profiles count: {len(profiles)}")
    for p in profiles[:3]:
        print(f"  Profile: {p.get('name')} (id: {p.get('id')})")
        print(f"    Profile locations: {json.dumps(p.get('profile_locations_count'))}")
        print(f"    Active: {p.get('active')}")
