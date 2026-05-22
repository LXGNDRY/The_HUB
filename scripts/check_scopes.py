#!/usr/bin/env python3
"""Check what scopes the current token has, and test shipping-related endpoints."""
import os, requests

SHOP = "lngndny.myshopify.com"
API_VERSION = "2024-01"
TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
H = {"X-Shopify-Access-Token": TOKEN}

# Check granted scopes
r = requests.get(f"https://{SHOP}/admin/oauth/access_scopes.json", headers=H)
print("Scopes response:", r.status_code)
if r.ok:
    scopes = [s["handle"] for s in r.json().get("access_scopes", [])]
    print("Granted scopes:")
    for s in sorted(scopes):
        print(f"  {s}")
else:
    print(r.text[:300])

# Test individual endpoints
tests = [
    ("locations.json", "Locations"),
    ("shipping_zones.json", "Shipping zones"),
    ("carrier_services.json", "Carrier services"),
    ("fulfillment_services.json", "Fulfillment services"),
    ("markets.json", "Markets"),
    ("delivery_profiles.json", "Delivery profiles"),
]
print("\nEndpoint access test:")
for path, label in tests:
    r = requests.get(f"https://{SHOP}/admin/api/{API_VERSION}/{path}", headers=H)
    print(f"  {label}: {r.status_code} {'✓' if r.ok else '✗'}")
    if r.ok:
        data = r.json()
        key = list(data.keys())[0]
        print(f"    → {len(data[key])} items")
