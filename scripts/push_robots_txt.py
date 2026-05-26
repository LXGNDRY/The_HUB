import os, requests, sys

TOKEN  = os.environ["SHOPIFY_ADMIN_TOKEN"]
DOMAIN = os.environ.get("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
API    = "2026-04"
BASE   = f"https://{DOMAIN}/admin/api/{API}"
HEADERS = {
    "X-Shopify-Access-Token": TOKEN,
    "Content-Type": "application/json"
}

# 1. Get active theme
r = requests.get(f"{BASE}/themes.json", headers=HEADERS, timeout=15)
r.raise_for_status()
active = next((t for t in r.json()["themes"] if t["role"] == "main"), None)
if not active:
    print("ERROR: No active theme found"); sys.exit(1)
theme_id = active["id"]
print(f"Active theme: {active['name']} (ID: {theme_id})")

# 2. robots.txt content
VALUE = open("scripts/robots_v2.liquid").read()

# 3. Push asset
r2 = requests.put(
    f"{BASE}/themes/{theme_id}/assets.json",
    headers=HEADERS,
    json={"asset": {"key": "templates/robots.txt.liquid", "value": VALUE}},
    timeout=30
)
if r2.status_code in (200, 201):
    asset = r2.json().get("asset", {})
    print(f"SUCCESS: robots.txt.liquid pushed to live theme")
    print(f"  Key: {asset.get('key')} | Updated: {asset.get('updated_at')}")
else:
    print(f"ERROR {r2.status_code}: {r2.text}"); sys.exit(1)
