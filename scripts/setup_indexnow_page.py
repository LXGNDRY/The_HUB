"""
setup_indexnow_page.py — One-shot: create the IndexNow key verification page on Shopify.

Obtains an access token via OAuth Client Credentials (SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET),
then uses it to create/update the page at /pages/{key} on the store.
"""

import os
import sys
import requests

INDEXNOW_KEY    = os.getenv("INDEXNOW_API_KEY", "")
SITE_DOMAIN     = os.getenv("SITE_DOMAIN", "legendary-branding.com")
STORE_DOMAIN    = os.getenv("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
ADMIN_TOKEN     = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID       = os.getenv("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET   = os.getenv("SHOPIFY_CLIENT_SECRET", "")
API_VERSION     = "2026-04"
BASE_URL        = f"https://{STORE_DOMAIN}/admin/api/{API_VERSION}"

if not INDEXNOW_KEY:
    print("ERROR: INDEXNOW_API_KEY not set.")
    sys.exit(1)

if not ADMIN_TOKEN and (not CLIENT_ID or not CLIENT_SECRET):
    print("ERROR: SHOPIFY_ADMIN_TOKEN, or both SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET, must be set.")
    sys.exit(1)

page_url = f"https://{SITE_DOMAIN}/pages/{INDEXNOW_KEY}"
print(f"IndexNow key : {INDEXNOW_KEY}")
print(f"Target URL   : {page_url}")
print(f"Store        : {STORE_DOMAIN}")

if ADMIN_TOKEN:
    print("Using SHOPIFY_ADMIN_TOKEN from env.")
    access_token = ADMIN_TOKEN
else:
    # --- Obtain access token via Client Credentials ---
    print("Obtaining access token via Client Credentials...")
    token_resp = requests.post(
        f"https://{STORE_DOMAIN}/admin/oauth/access_token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=15,
    )
    if not token_resp.ok:
        print(f"ERROR {token_resp.status_code} obtaining token: {token_resp.text[:500]}")
        sys.exit(1)

    token_data = token_resp.json()
    access_token = token_data.get("access_token", "")
    if not access_token:
        print(f"ERROR: No access_token in response: {token_data}")
        sys.exit(1)

    print("Access token obtained.")

HEADERS = {
    "X-Shopify-Access-Token": access_token,
    "Content-Type": "application/json",
}


def shopify_get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=15)
    if not r.ok:
        print(f"ERROR {r.status_code} on GET {path}: {r.text[:500]}")
        r.raise_for_status()
    return r.json()


def shopify_post(path, body):
    r = requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=body, timeout=15)
    if not r.ok:
        print(f"ERROR {r.status_code} on POST {path}: {r.text[:500]}")
        r.raise_for_status()
    return r.json()


def shopify_put(path, body):
    r = requests.put(f"{BASE_URL}{path}", headers=HEADERS, json=body, timeout=15)
    if not r.ok:
        print(f"ERROR {r.status_code} on PUT {path}: {r.text[:500]}")
        r.raise_for_status()
    return r.json()


# Check if page already exists
existing = shopify_get("/pages.json", {"limit": 250}).get("pages", [])
for p in existing:
    if p.get("handle") == INDEXNOW_KEY:
        print(f"Page already exists (id={p['id']}) — updating body to ensure key is correct.")
        shopify_put(f"/pages/{p['id']}.json", {"page": {"id": p["id"], "body_html": INDEXNOW_KEY}})
        print("✅ Done.")
        sys.exit(0)

# Create new page
result = shopify_post("/pages.json", {
    "page": {
        "title": "IndexNow Key Verification",
        "body_html": INDEXNOW_KEY,
        "published": True,
    }
})
page = result.get("page", {})
page_id = page.get("id")

if not page_id:
    print(f"ERROR: Page creation failed: {result}")
    sys.exit(1)

# Set the handle to the key string so the URL is /pages/{key}
shopify_put(f"/pages/{page_id}.json", {"page": {"id": page_id, "handle": INDEXNOW_KEY}})

print(f"✅ Page created (id={page_id})")
print(f"   URL: {page_url}")
