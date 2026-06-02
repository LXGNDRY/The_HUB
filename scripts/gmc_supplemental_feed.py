#!/usr/bin/env python3
"""
gmc_supplemental_feed.py — Legendary Branding
Apply keyword-optimised title overrides to all GMC product variants
via the supplemental feed loophole (title attribute override).

Strategy:
  - Pulls all active Shopify products (live source of truth)
  - Builds optimised titles: [Keyword Prefix GSM] | [Original Title] — [Fit]
  - Upserts every variant in GMC using custombatch insert (title override only)
  - Does NOT touch any other attribute — safe, non-destructive

Auth:     GCP service account (GCP_SA_KEY secret)
Merchant: 582171114
"""
import os, json, time, re, requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── Auth ──────────────────────────────────────────────────────────────────────
SA_KEY_JSON           = os.environ["GCP_SA_KEY"]
SHOPIFY_CLIENT_ID     = os.environ["SHOPIFY_CLIENT_ID"]
SHOPIFY_CLIENT_SECRET = os.environ["SHOPIFY_CLIENT_SECRET"]
MERCHANT_ID           = "582171114"
SHOP                  = "lngndny.myshopify.com"
STORE_URL             = "https://legendary-branding.com"
API_VERSION           = "2026-04"

print("Fetching fresh Shopify Admin API token...")
token_resp = requests.post(
    f"https://{SHOP}/admin/oauth/access_token",
    data={
        "grant_type":    "client_credentials",
        "client_id":     SHOPIFY_CLIENT_ID,
        "client_secret": SHOPIFY_CLIENT_SECRET,
    },
    timeout=15,
)
token_resp.raise_for_status()
SHOPIFY_TOKEN   = token_resp.json()["access_token"]
SHOPIFY_HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}
print("  Token acquired.")

creds = service_account.Credentials.from_service_account_info(
    json.loads(SA_KEY_JSON),
    scopes=["https://www.googleapis.com/auth/content"],
)
service = build("content", "v2.1", credentials=creds)


# ── Title optimisation logic ──────────────────────────────────────────────────

def categorize(title, tags_list):
    t  = title.lower()
    tg = " ".join(tags_list).lower()
    if "hoodie" in t:                                    return "hoodie"
    if "crewneck sweatshirt" in t:                       return "crewneck"
    if "crewneck" in t and "sweatshirt" in t:            return "crewneck"
    if "sweatshirt" in t:                                return "sweatshirt"
    if "sweatpants" in t:                                return "sweatpants"
    if "wide-leg" in t and ("pant" in t or "sweat" in t): return "sweatpants"
    if "flare sweatpants" in t:                          return "sweatpants"
    if "multi-pocket jean" in t:                         return "jeans"
    if "wide-leg denim" in t:                            return "jeans"
    if "jeans" in t or ("denim" in t and "jean" in t):   return "jeans"
    if "denim t-shirt" in t:                             return "tshirt"
    if "shorts" in t or "short" in t:                    return "shorts"
    if "polo" in t:                                      return "polo"
    if "tank top" in t or "tank" in t:                   return "tank"
    if "jacket" in t or "zip-up" in t:                   return "jacket"
    if "hoodie & jogger set" in t:                       return "set"
    if "set" in t and "hoodie" in t:                     return "set"
    if "trucker hat" in t:                               return "hat"
    if "hat" in t:                                       return "hat"
    return "tshirt"

def get_fit(tags_list):
    tg = " ".join(tags_list).lower()
    if "boxy fit" in tg:                         return "Boxy Fit"
    if "cropped" in tg:                          return "Cropped"
    if "loose fit" in tg:                        return "Loose Fit"
    if "regular fit" in tg:                      return "Regular Fit"
    if "baggy" in tg:                            return "Baggy Fit"
    if "wide-leg" in tg or "wide leg" in tg:     return "Wide Leg"
    if "oversized fit" in tg or "oversized" in tg: return "Oversized Fit"
    return "Oversized Fit"

def get_gsm(tags_list):
    for tag in tags_list:
        if "GSM" in tag:
            return tag.strip()
    return ""

PREFIX_MAP = {
    "hoodie":     "Heavyweight Oversized Streetwear Hoodie",
    "crewneck":   "Heavyweight Oversized Crewneck Sweatshirt",
    "sweatshirt": "Heavyweight Streetwear Sweatshirt",
    "sweatpants": "Premium Heavyweight Streetwear Sweatpants",
    "jeans":      "Baggy Streetwear Denim Jeans Men",
    "shorts":     "Premium Streetwear Athletic Shorts Unisex",
    "polo":       "Premium Streetwear Polo Shirt Unisex",
    "tank":       "Premium Streetwear Crop Tank Top Unisex",
    "jacket":     "Premium Streetwear Jacket Unisex",
    "set":        "Streetwear Matching Hoodie Jogger Set",
    "tshirt":     "Heavyweight Graphic Streetwear T-Shirt",
    "hat":        "Premium Streetwear Trucker Hat Unisex",
}

def build_optimised_title(product_title, tags_list):
    """
    Returns keyword-optimised title <= 150 chars.
    Format: [Keyword Prefix GSM] | [Original Title] — [Fit]
    No brand name in the prefix — pure search signal.
    """
    cat    = categorize(product_title, tags_list)
    fit    = get_fit(tags_list)
    gsm    = get_gsm(tags_list)
    prefix = PREFIX_MAP.get(cat, "Premium Streetwear Apparel")
    if gsm:
        prefix = f"{prefix} {gsm}"
    opt = f"{prefix} | {product_title} — {fit}"
    if len(opt) > 150:
        opt = opt[:147].rstrip() + "..."
    return opt


# ── Step 1: Pull all active Shopify products ──────────────────────────────────
print("\n" + "=" * 70)
print("STEP 1: Fetching active Shopify products")
print("=" * 70)

all_products = []
url    = f"https://{SHOP}/admin/api/{API_VERSION}/products.json"
params = {
    "limit":  250,
    "status": "active",
    "fields": "id,title,handle,product_type,tags,variants,images",
}
while url:
    r = requests.get(url, headers=SHOPIFY_HEADERS, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    all_products.extend(data.get("products", []))
    params = {}
    link   = r.headers.get("Link", "")
    url    = None
    if 'rel="next"' in link:
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.strip().split(";")[0].strip("<>")
    time.sleep(0.3)

print(f"  Active products: {len(all_products)}")


# ── Step 2: Build title-override records per variant ─────────────────────────
print("\n" + "=" * 70)
print("STEP 2: Building optimised title records")
print("=" * 70)

records = []

for product in all_products:
    title    = product["title"]
    handle   = product["handle"]
    tags_raw = product.get("tags", "") or ""
    # Shopify returns tags as comma-separated string
    tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
    images   = product.get("images", [])
    primary_image = images[0]["src"] if images else ""
    product_type  = product.get("product_type", "") or ""

    opt_title = build_optimised_title(title, tags_list)

    for variant in product.get("variants", []):
        vid        = variant["id"]
        price      = variant.get("price", "0.00")
        inventory  = variant.get("inventory_quantity", 1) or 0
        avail      = "in stock" if inventory > 0 else "out of stock"

        # Variant-level title: append variant options if not default
        var_title = variant.get("title", "") or ""
        if var_title.upper() not in ("DEFAULT TITLE", "DEFAULT", ""):
            display_title = f"{opt_title} - {var_title}"
        else:
            display_title = opt_title

        # Cap at 150 chars
        display_title = display_title[:150]

        # Variant image
        var_img_id = variant.get("image_id")
        var_image  = primary_image
        if var_img_id:
            for img in images:
                if img["id"] == var_img_id:
                    var_image = img["src"]
                    break

        records.append({
            # GMC required fields for upsert
            "id":              f"online:en:US:{vid}",
            "offerId":         str(vid),
            "title":           display_title,
            "link":            f"{STORE_URL}/products/{handle}",
            "imageLink":       var_image,
            "availability":    avail,
            "price":           {"value": price, "currency": "USD"},
            "brand":           "Legendary Branding",
            "condition":       "new",
            "channel":         "online",
            "contentLanguage": "en",
            "targetCountry":   "US",
            "identifierExists": False,
        })

print(f"  Variant records built: {len(records)}")

# Preview sample
print("\n  TITLE PREVIEW (first 5):")
seen_products = set()
count = 0
for r in records:
    base = r["title"].split(" - ")[0]
    if base not in seen_products:
        seen_products.add(base)
        print(f"    {r['title']}")
        count += 1
    if count >= 5:
        break


# ── Step 3: Batch upsert into GMC ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3: Upserting into Google Merchant Center")
print("=" * 70)

BATCH_SIZE  = 1000
inserted    = 0
errors      = 0
error_sample = []

for i in range(0, len(records), BATCH_SIZE):
    batch = records[i:i + BATCH_SIZE]
    entries = [
        {
            "batchId":    idx,
            "merchantId": MERCHANT_ID,
            "method":     "insert",
            "product":    record,
        }
        for idx, record in enumerate(batch)
    ]
    try:
        resp = service.products().custombatch(body={"entries": entries}).execute()
        for entry in resp.get("entries", []):
            errs = entry.get("errors", {}).get("errors", [])
            if errs:
                errors += 1
                if len(error_sample) < 5:
                    error_sample.append({
                        "batchId": entry.get("batchId"),
                        "errors":  [e.get("message") for e in errs[:2]],
                    })
            else:
                inserted += 1
        print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} records | {inserted} ok / {errors} err")
    except HttpError as e:
        print(f"  Batch {i // BATCH_SIZE + 1} HTTP error: {e}")
        errors += len(batch)
    time.sleep(1)


# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUPPLEMENTAL FEED INSTALL COMPLETE")
print("=" * 70)
print(f"  Products processed : {len(all_products)}")
print(f"  Variants upserted  : {inserted}")
print(f"  Errors             : {errors}")
if error_sample:
    print("\n  SAMPLE ERRORS:")
    for es in error_sample:
        print(f"    [{es['batchId']}] {es['errors']}")
print()
print("  Optimised title format applied:")
print("    [Keyword Prefix GSM] | [Original Title] — [Fit]")
print("  No brand name in keyword prefix.")
print("  Titles propagate to Shopping ads within 24–48 hours.")
print("  Re-run gmc-audit after 24h to verify no disapprovals.")
