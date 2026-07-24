"""
setup_indexnow_page.py — One-shot: create the IndexNow key verification page on Shopify.

Uses the Shopify Admin REST API directly with SHOPIFY_ADMIN_TOKEN.
Requires the custom app to have 'write_content' scope (Online Store > Pages).

If the REST Pages API returns 401/403, the script prints instructions for
enabling the scope in the Shopify admin custom app settings.
"""

import os
import sys
import json
import requests

INDEXNOW_KEY   = os.getenv("INDEXNOW_API_KEY", "")
SITE_DOMAIN    = os.getenv("SITE_DOMAIN", "legendary-branding.com")
STORE_DOMAIN   = os.getenv("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
ADMIN_TOKEN    = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
API_VERSION    = "2026-04"
BASE_URL       = f"https://{STORE_DOMAIN}/admin/api/{API_VERSION}"

if not INDEXNOW_KEY:
    print("ERROR: INDEXNOW_API_KEY not set.")
    sys.exit(1)

if not ADMIN_TOKEN:
    print("ERROR: SHOPIFY_ADMIN_TOKEN not set.")
    sys.exit(1)

HEADERS = {
    "X-Shopify-Access-Token": ADMIN_TOKEN,
    "Content-Type": "application/json",
}

page_url = f"https://{SITE_DOMAIN}/pages/{INDEXNOW_KEY}"
print(f"IndexNow key : {INDEXNOW_KEY}")
print(f"Target URL   : {page_url}")
print(f"Store        : {STORE_DOMAIN}")


def shopify_get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params, timeout=15)
    if not r.ok:
        print(f"ERROR {r.status_code} on GET {path}: {r.text[:500]}")
        if r.status_code in (401, 403):
            print()
            print("SCOPE FIX REQUIRED:")
            print("  1. Go to Shopify Admin > Apps > Develop apps > your custom app")
            print("  2. Click 'Configure Admin API scopes'")
            print("  3. Enable 'write_content' (and 'read_content') under Online Store")
            print("  4. Click Save, then reinstall the app to get a new token")
            print("  5. Update the SHOPIFY_ADMIN_TOKEN secret in GitHub")
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
