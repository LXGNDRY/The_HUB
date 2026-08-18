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

def gql(query, variables=None):
    r = requests.post(GQL_URL, headers=HEADERS, json={"query": query, "variables": variables or {}})
    r.raise_for_status()
    return r.json()

# Pull first 50 products with variant SKU/barcode data
Q = """
query($cursor: String) {
  products(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      title
      productType
      vendor
      variants(first: 10) {
        nodes {
          id
          sku
          barcode
          title
          price
        }
      }
    }
  }
}
"""

all_products = []
cursor = None
while True:
    data = gql(Q, {"cursor": cursor})
    nodes = data["data"]["products"]["nodes"]
    all_products.extend(nodes)
    page = data["data"]["products"]["pageInfo"]
    if not page["hasNextPage"]:
        break
    cursor = page["endCursor"]
    if len(all_products) >= 200:  # cap for audit
        break

# Analyze
no_sku = []
has_sku = []
has_barcode = []
no_product_type = []
product_types = {}

for p in all_products:
    has_type = bool(p.get("productType", "").strip())
    if not has_type:
        no_product_type.append(p["title"])
    pt = p.get("productType", "(none)").strip() or "(none)"
    product_types[pt] = product_types.get(pt, 0) + 1

    for v in p["variants"]["nodes"]:
        sku = (v.get("sku") or "").strip()
        barcode = (v.get("barcode") or "").strip()
        label = f"{p['title']} — {v['title']}"
        if sku:
            has_sku.append(label)
        else:
            no_sku.append(label)
        if barcode:
            has_barcode.append(label)

total_variants = len(has_sku) + len(no_sku)

print("=" * 60)
print(f"PRODUCTS AUDITED: {len(all_products)}")
print(f"TOTAL VARIANTS:   {total_variants}")
print("=" * 60)

print(f"\nSKU COVERAGE:")
print(f"  With SKU:    {len(has_sku)} ({len(has_sku)/total_variants*100:.1f}%)")
print(f"  Missing SKU: {len(no_sku)} ({len(no_sku)/total_variants*100:.1f}%)")

print(f"\nBARCODE/GTIN COVERAGE:")
print(f"  With barcode: {len(has_barcode)} ({len(has_barcode)/total_variants*100:.1f}%)")
print(f"  Missing:      {total_variants - len(has_barcode)}")

print(f"\nPRODUCT TYPE COVERAGE:")
print(f"  Missing product type: {len(no_product_type)}")
print(f"  Unique types found:   {len(product_types)}")
for pt, count in sorted(product_types.items(), key=lambda x: -x[1])[:15]:
    print(f"    [{count:3d}] {pt}")

print(f"\nFIRST 20 VARIANTS MISSING SKU:")
for v in no_sku[:20]:
    print(f"  - {v}")
