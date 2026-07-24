"""
setup_indexnow_page.py — One-shot: create the IndexNow key verification page on Shopify.

IndexNow requires a file at https://{domain}/{key}.txt  OR  anywhere you specify
via the keyLocation field in API submissions. Shopify can't serve arbitrary .txt
files at the root, so we:
  1. Create a Shopify page whose URL handle is the IndexNow key.
  2. The page body is just the key string (plain text, no HTML wrapping).
  3. Our IndexNow API calls include keyLocation pointing at this page.

Page URL: https://legendary-branding.com/pages/{INDEXNOW_API_KEY}
keyLocation in API calls: https://legendary-branding.com/pages/{INDEXNOW_API_KEY}

Run once; safe to re-run (checks for an existing page first).
"""

import os
import sys

INDEXNOW_KEY = os.getenv("INDEXNOW_API_KEY", "")
SITE_DOMAIN  = os.getenv("SITE_DOMAIN", "legendary-branding.com")

if not INDEXNOW_KEY:
    print("ERROR: INDEXNOW_API_KEY not set.")
    sys.exit(1)

from modules.shopify import list_pages, create_page, update_page

page_url = f"https://{SITE_DOMAIN}/pages/{INDEXNOW_KEY}"
print(f"IndexNow key : {INDEXNOW_KEY}")
print(f"Target URL   : {page_url}")

# Check if page already exists
existing = list_pages(limit=250).get("pages", [])
for p in existing:
    if p.get("handle") == INDEXNOW_KEY:
        print(f"Page already exists (id={p['id']}) — updating body to ensure key is correct.")
        update_page(p["id"], {"body_html": INDEXNOW_KEY})
        print("✅ Done.")
        sys.exit(0)

# Create new page
result = create_page(
    title="IndexNow Key Verification",
    body_html=INDEXNOW_KEY,
    published=True,
)
page = result.get("page", {})
page_id = page.get("id")

if not page_id:
    print(f"ERROR: Page creation failed: {result}")
    sys.exit(1)

# Set the handle to the key string so the URL is /pages/{key}
update_page(page_id, {"handle": INDEXNOW_KEY})

print(f"✅ Page created (id={page_id})")
print(f"   URL: {page_url}")
print(f"   Use keyLocation={page_url} in IndexNow API submissions.")
