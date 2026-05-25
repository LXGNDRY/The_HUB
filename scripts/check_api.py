import os, requests, json

SHOP = "lngndny.myshopify.com"
TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

# Test 1: list products — check what fields come back
r = requests.get(f"https://{SHOP}/admin/api/2024-10/products.json?limit=5&fields=id,handle,status", headers=HEADERS)
print(f"REST list status: {r.status_code}")
print(json.dumps(r.json(), indent=2)[:1000])

# Test 2: try handle filter specifically
r2 = requests.get(f"https://{SHOP}/admin/api/2024-10/products.json?handle=goat-hoodie-440gsm", headers=HEADERS)
print(f"\nHandle filter status: {r2.status_code}")
print(json.dumps(r2.json(), indent=2)[:500])

# Test 3: GraphQL — get product by handle
query = """
{
  productByHandle(handle: "goat-hoodie-440gsm") {
    id
    handle
    status
    tags
  }
}
"""
r3 = requests.post(
    f"https://{SHOP}/admin/api/2024-10/graphql.json",
    headers=HEADERS,
    json={"query": query}
)
print(f"\nGraphQL status: {r3.status_code}")
print(json.dumps(r3.json(), indent=2)[:500])
