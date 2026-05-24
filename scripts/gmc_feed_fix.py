#!/usr/bin/env python3
"""
gmc_feed_fix.py
Fix 1: Delete all non-active/non-Shopify products from GMC feed
Fix 2: Patch brand = "Legendary Branding" on all remaining products
Fix 3: Set identifier_exists = false where GTIN is missing (apparel exemption)
Fix 4: Fix shipping — clean slate US shipping rule
Uses GCP_SA_KEY + SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET
Fetches a fresh Shopify Admin API token at runtime (tokens expire every 24h)
"""
import os, json, sys, time, requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── Auth ─────────────────────────────────────────────────────
SA_KEY_JSON = os.environ["GCP_SA_KEY"]
SHOPIFY_CLIENT_ID = os.environ["SHOPIFY_CLIENT_ID"]
SHOPIFY_CLIENT_SECRET = os.environ["SHOPIFY_CLIENT_SECRET"]
MERCHANT_ID = "582171114"
SHOP = "lngndny.myshopify.com"
API_VERSION = "2026-04"

# Fetch a fresh token via client credentials grant (valid 24h)
print("Fetching fresh Shopify Admin API token...")
token_resp = requests.post(
    f"https://{SHOP}/admin/oauth/access_token",
    data={
        "grant_type": "client_credentials",
        "client_id": SHOPIFY_CLIENT_ID,
        "client_secret": SHOPIFY_CLIENT_SECRET,
    }
)
token_resp.raise_for_status()
SHOPIFY_TOKEN = token_resp.json()["access_token"]
print(f"  Token acquired (scopes: {token_resp.json().get('scope', 'unknown')})")
SHOPIFY_HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}

creds = service_account.Credentials.from_service_account_info(
    json.loads(SA_KEY_JSON),
    scopes=["https://www.googleapis.com/auth/content"]
)
service = build("content", "v2.1", credentials=creds)

# ── Step 1: Get active Shopify product handles ───────────────
print("=" * 70)
print("STEP 1: Fetching active Shopify products")
print("=" * 70)

shopify_active_ids = set()
url = f"https://{SHOP}/admin/api/{API_VERSION}/products.json"
params = {"limit": 250, "status": "active", "fields": "id,handle,variants"}
while url:
    r = requests.get(url, headers=SHOPIFY_HEADERS, params=params)
    r.raise_for_status()
    data = r.json()
    for p in data.get("products", []):
        for v in p.get("variants", []):
            shopify_active_ids.add(str(v["id"]))
    link = r.headers.get("Link", "")
    url, params = None, {}
    if 'rel="next"' in link:
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.strip().split(";")[0].strip("<>")
    time.sleep(0.3)

print(f"  Active Shopify variant IDs: {len(shopify_active_ids)}")

# ── Step 2: Pull all GMC products ────────────────────────────
print("\n" + "=" * 70)
print("STEP 2: Pulling GMC feed products")
print("=" * 70)

all_gmc = []
req = service.products().list(merchantId=MERCHANT_ID, maxResults=250)
while req:
    res = req.execute()
    all_gmc.extend(res.get("resources", []))
    req = service.products().list_next(req, res)

print(f"  Total GMC products: {len(all_gmc)}")

# ── Step 3: Classify — keep vs delete ────────────────────────
# GMC product IDs from Shopify look like: online:en:US:shopify_variant_id
# or shopify_US_en_VARIANT_ID — extract the numeric variant ID
import re

to_delete = []
to_update = []

for p in all_gmc:
    pid = p.get("id", "")
    # Extract variant ID from the GMC product ID
    variant_match = re.search(r'(\d{10,})', pid)
    variant_id = variant_match.group(1) if variant_match else None
    
    if variant_id and variant_id in shopify_active_ids:
        to_update.append(p)
    else:
        to_delete.append(p)

print(f"  To keep & update: {len(to_update)}")
print(f"  To delete:        {len(to_delete)}")

# ── Step 4: Delete non-active products in batches ────────────
print("\n" + "=" * 70)
print("STEP 3: Deleting non-active products")
print("=" * 70)

BATCH_SIZE = 1000
deleted = 0
errors = 0

for i in range(0, len(to_delete), BATCH_SIZE):
    batch = to_delete[i:i+BATCH_SIZE]
    entries = [
        {"batchId": idx, "merchantId": MERCHANT_ID, "method": "delete", "productId": p["id"]}
        for idx, p in enumerate(batch)
    ]
    try:
        resp = service.products().custombatch(
            body={"entries": entries}
        ).execute()
        for entry in resp.get("entries", []):
            if entry.get("errors"):
                errors += 1
            else:
                deleted += 1
        print(f"  Batch {i//BATCH_SIZE + 1}: deleted {len(batch)} products")
    except HttpError as e:
        print(f"  Batch error: {e}")
    time.sleep(1)

print(f"  Total deleted: {deleted} | Errors: {errors}")

# ── Step 5: Patch active products — brand + identifier_exists ─
print("\n" + "=" * 70)
print("STEP 4: Patching active products (brand + identifier_exists)")
print("=" * 70)

patched = 0
patch_errors = 0

for i in range(0, len(to_update), BATCH_SIZE):
    batch = to_update[i:i+BATCH_SIZE]
    entries = []
    for idx, p in enumerate(batch):
        updated = dict(p)
        updated["brand"] = "Legendary Branding"
        if not updated.get("gtin"):
            updated["identifierExists"] = False
        entries.append({
            "batchId": idx,
            "merchantId": MERCHANT_ID,
            "method": "update",
            "productId": p["id"],
            "product": updated,
            "updateMask": "brand,identifierExists"
        })
    try:
        resp = service.products().custombatch(body={"entries": entries}).execute()
        for entry in resp.get("entries", []):
            if entry.get("errors"):
                patch_errors += 1
            else:
                patched += 1
        print(f"  Batch {i//BATCH_SIZE + 1}: patched {len(batch)} products")
    except HttpError as e:
        print(f"  Batch patch error: {e}")
    time.sleep(1)

print(f"  Total patched: {patched} | Errors: {patch_errors}")


# ── Step 6: Fix shipping — global services ────────────────────
print("\n" + "=" * 70)
print("STEP 5: Fixing shipping settings (US + International)")
print("=" * 70)

def make_service(name, country, currency, flat_rate, free_threshold=None,
                 min_transit=7, max_transit=21, min_handle=1, max_handle=3):
    """Build a GMC shipping service dict."""
    svc = {
        "name": name,
        "active": True,
        "deliveryCountry": country,
        "currency": currency,
        "deliveryTime": {
            "minHandlingTimeInDays": min_handle,
            "maxHandlingTimeInDays": max_handle,
            "minTransitTimeInDays": min_transit,
            "maxTransitTimeInDays": max_transit,
        },
        "rateGroups": [
            {
                "name": "Rate",
                "singleValue": {"flatRate": {"value": str(flat_rate), "currency": currency}}
            }
        ]
    }
    if free_threshold is not None:
        svc["minimumOrderValue"] = {"value": str(free_threshold), "currency": currency}
        svc["rateGroups"][0]["singleValue"]["flatRate"]["value"] = "0.00"
    return svc

# ── Shipping strategy (profit-optimized) ─────────────────────
# US:           $5.99 standard  | FREE on $100+   (3–7 days)
# Tier 1 - English-speaking + EU core:
#   CA/UK/AU/NZ: $14.99 standard | FREE on $150+  (7–14 days)
#   DE/FR/NL/SE/AT/IE: $19.99   | FREE on $150+  (7–21 days)
# Tier 2 - Asia/Pacific:
#   JP/SG:       $19.99          | FREE on $175+  (7–21 days)
# Rest of World: $24.99 flat, no free threshold   (10–30 days)
#
# Logic: free threshold slightly above typical AOV (~$85–95) to
# incentivize add-to-cart upsell without giving away margin.
# International rates baked in to protect contribution margin
# (actual USPS/DHL First Class ~$12–18 for apparel weight).

USD = "USD"

services = [
    # ── US ───────────────────────────────────────────────────
    make_service("Standard US Shipping",      "US", USD, 5.99,  min_transit=3, max_transit=7),
    make_service("Free Shipping US ($100+)",  "US", USD, 0.00,  free_threshold=100.00, min_transit=3, max_transit=7),

    # ── Tier 1: English-speaking ────────────────────────────
    make_service("Standard Shipping CA",      "CA", USD, 14.99),
    make_service("Free Shipping CA ($150+)",  "CA", USD, 0.00,  free_threshold=150.00),
    make_service("Standard Shipping GB",      "GB", USD, 14.99),
    make_service("Free Shipping GB ($150+)",  "GB", USD, 0.00,  free_threshold=150.00),
    make_service("Standard Shipping AU",      "AU", USD, 14.99),
    make_service("Free Shipping AU ($150+)",  "AU", USD, 0.00,  free_threshold=150.00),
    make_service("Standard Shipping NZ",      "NZ", USD, 14.99),
    make_service("Free Shipping NZ ($150+)",  "NZ", USD, 0.00,  free_threshold=150.00),
    make_service("Standard Shipping IE",      "IE", USD, 14.99),
    make_service("Free Shipping IE ($150+)",  "IE", USD, 0.00,  free_threshold=150.00),

    # ── Tier 1: Core EU ─────────────────────────────────────
    make_service("Standard Shipping DE",      "DE", USD, 19.99),
    make_service("Free Shipping DE ($150+)",  "DE", USD, 0.00,  free_threshold=150.00),
    make_service("Standard Shipping FR",      "FR", USD, 19.99),
    make_service("Free Shipping FR ($150+)",  "FR", USD, 0.00,  free_threshold=150.00),
    make_service("Standard Shipping NL",      "NL", USD, 19.99),
    make_service("Free Shipping NL ($150+)",  "NL", USD, 0.00,  free_threshold=150.00),
    make_service("Standard Shipping SE",      "SE", USD, 19.99),
    make_service("Free Shipping SE ($150+)",  "SE", USD, 0.00,  free_threshold=150.00),
    make_service("Standard Shipping AT",      "AT", USD, 19.99),
    make_service("Free Shipping AT ($150+)",  "AT", USD, 0.00,  free_threshold=150.00),

    # ── Tier 2: Asia/Pacific ────────────────────────────────
    make_service("Standard Shipping JP",      "JP", USD, 19.99),
    make_service("Free Shipping JP ($175+)",  "JP", USD, 0.00,  free_threshold=175.00, max_transit=21),
    make_service("Standard Shipping SG",      "SG", USD, 19.99),
    make_service("Free Shipping SG ($175+)",  "SG", USD, 0.00,  free_threshold=175.00, max_transit=21),
]

shipping_body = {
    "accountId": MERCHANT_ID,
    "services": services
}

try:
    resp = service.shippingsettings().update(
        merchantId=MERCHANT_ID,
        accountId=MERCHANT_ID,
        body=shipping_body
    ).execute()
    svc_count = len(resp.get("services", []))
    print(f"  Shipping updated — {svc_count} service(s) configured")
    for svc in resp.get("services", []):
        country = svc.get("deliveryCountry", "?")
        name = svc.get("name", "?")
        rate = svc.get("rateGroups", [{}])[0].get("singleValue", {}).get("flatRate", {}).get("value", "?")
        mo = svc.get("minimumOrderValue", {}).get("value", "")
        label = f"FREE (min ${mo})" if mo else f"${rate}"
        print(f"    [{country}] {name}: {label}")
except HttpError as e:
    print(f"  Shipping update error: {e}")

print("\n" + "=" * 70)
print("FEED FIX COMPLETE")
print("=" * 70)
print(f"  Deleted:  {deleted}")
print(f"  Patched:  {patched}")
print("  Next: Re-run audit in ~24h to verify approvals")
