import os, json, sys
import requests

token = os.environ["SHOPIFY_ADMIN_TOKEN"]
domain = "lngndny.myshopify.com"
api = "2026-04"
base = "https://{}/admin/api/{}".format(domain, api)
headers = {
    "X-Shopify-Access-Token": token,
    "Content-Type": "application/json"
}

print("Step 1: Get active theme...")
r = requests.get(base + "/themes.json", headers=headers, timeout=15)
print("Themes status:", r.status_code)
r.raise_for_status()
themes = r.json()["themes"]
active = next((t for t in themes if t["role"] == "main"), None)
if not active:
    print("ERROR: No active theme")
    sys.exit(1)
theme_id = active["id"]
print("Active theme: {} ({})".format(active["name"], theme_id))

print("Step 2: Reading robots_v2.liquid...")
value = open("scripts/robots_v2.liquid").read()
print("File length:", len(value), "chars")

print("Step 3: Pushing asset to theme {}...".format(theme_id))
payload = {"asset": {"key": "templates/robots.txt.liquid", "value": value}}
url = "{}/themes/{}/assets.json".format(base, theme_id)
r2 = requests.put(url, headers=headers, json=payload, timeout=30)
print("Asset PUT status:", r2.status_code)
if r2.status_code in (200, 201):
    asset = r2.json().get("asset", {})
    print("SUCCESS: {} updated at {}".format(asset.get("key"), asset.get("updated_at")))
else:
    print("FAILED:", r2.text[:500])
    sys.exit(1)
