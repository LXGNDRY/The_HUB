import os, requests, json

SHOP = "lngndny.myshopify.com"
TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
API = f"https://{SHOP}/admin/api/2024-10"
HEADERS = {"X-Shopify-Access-Token": TOKEN}

# Test with a known handle
r = requests.get(f"{API}/products.json?handle=goat-hoodie-440gsm&fields=id,handle,tags", headers=HEADERS)
print(f"Status: {r.status_code}")
print(json.dumps(r.json(), indent=2))

# Also try listing first few products to confirm API works
r2 = requests.get(f"{API}/products.json?limit=3&fields=id,handle", headers=HEADERS)
print(f"\nProduct list status: {r2.status_code}")
print(json.dumps(r2.json(), indent=2)[:500])
