#!/usr/bin/env python3
"""
dump_product_handles.py
Fetches all active products with id, title, and handle from Shopify.
Outputs JSON to stdout and saves to /tmp/product_handles.json for inspection.
"""

import os, json, requests, time

SHOP = "lngndny.myshopify.com"
API_VERSION = "2024-01"
TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

products = []
url = f"https://{SHOP}/admin/api/{API_VERSION}/products.json"
params = {"limit": 250, "status": "active", "fields": "id,title,handle"}

while url:
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    data = resp.json()
    batch = data.get("products", [])
    products.extend(batch)
    link = resp.headers.get("Link", "")
    url, params = None, {}
    if 'rel="next"' in link:
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break
    time.sleep(0.3)

print(f"Total products: {len(products)}")
for p in sorted(products, key=lambda x: x.get("title","").lower()):
    print(f"  [{p['id']}] handle={p['handle']!r:80s} title={p['title']!r}")

with open("/tmp/product_handles.json", "w") as f:
    json.dump(products, f, indent=2)
print("\nSaved to /tmp/product_handles.json")
