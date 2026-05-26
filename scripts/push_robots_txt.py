import os, json, sys
import urllib.request, urllib.error

token = os.environ["SHOPIFY_ADMIN_TOKEN"]
domain = "lngndny.myshopify.com"
api = "2026-04"
base = "https://{}/admin/api/{}".format(domain, api)
headers = {
    "X-Shopify-Access-Token": token,
    "Content-Type": "application/json"
}

print("Step 1: Get active theme...")
req = urllib.request.Request(base + "/themes.json", headers=headers)
with urllib.request.urlopen(req, timeout=15) as r:
    themes = json.loads(r.read())["themes"]

active = next((t for t in themes if t["role"] == "main"), None)
if not active:
    print("ERROR: No active theme")
    sys.exit(1)
theme_id = active["id"]
print("Active theme: {} ({})".format(active["name"], theme_id))

print("Step 2: Reading robots_v2.liquid...")
value = open("scripts/robots_v2.liquid").read()
print("File length: {} chars".format(len(value)))

print("Step 3: Pushing asset...")
body = json.dumps({"asset": {"key": "templates/robots.txt.liquid", "value": value}}).encode()
url = "{}/themes/{}/assets.json".format(base, theme_id)
req2 = urllib.request.Request(url, data=body, headers=headers, method="PUT")
try:
    with urllib.request.urlopen(req2, timeout=30) as r2:
        resp = json.loads(r2.read())
        asset = resp.get("asset", {})
        print("SUCCESS: {} updated at {}".format(asset.get("key"), asset.get("updated_at")))
except urllib.error.HTTPError as e:
    body_err = e.read().decode()
    print("HTTP ERROR {}: {}".format(e.code, body_err))
    sys.exit(1)
