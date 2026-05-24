#!/usr/bin/env python3
"""
gmc_feed_populate.py — Legendary Branding
Insert all active Shopify product variants into Google Merchant Center.

Pulls live products from Shopify Admin API (client credentials token),
builds a Content API v2.1 product record per variant, and batch-inserts
into GMC merchant ID 582171114.

Product ID format: online:en:US:{variant_id}
Required fields per Google Shopping:  id, title, description, link,
imageLink, availability, price, brand, condition, googleProductCategory.
"""
import os, json, time, re, requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── Auth ──────────────────────────────────────────────────────────────────────
SA_KEY_JSON        = os.environ["GCP_SA_KEY"]
SHOPIFY_CLIENT_ID  = os.environ["SHOPIFY_CLIENT_ID"]
SHOPIFY_CLIENT_SECRET = os.environ["SHOPIFY_CLIENT_SECRET"]
MERCHANT_ID        = "582171114"
SHOP               = "lngndny.myshopify.com"
STORE_URL          = "https://legendary-branding.com"
API_VERSION        = "2026-04"

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

# ── Step 1: Pull all active Shopify products ──────────────────────────────────
print("\n" + "=" * 70)
print("STEP 1: Fetching active Shopify products")
print("=" * 70)

all_products = []
url    = f"https://{SHOP}/admin/api/{API_VERSION}/products.json"
params = {
    "limit":  250,
    "status": "active",
    "fields": "id,title,body_html,handle,product_type,tags,variants,images,vendor",
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

# ── Step 2: Build GMC product records ────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 2: Building GMC product records")
print("=" * 70)

def strip_html(html):
    """Minimal HTML stripper — removes tags, collapses whitespace."""
    clean = re.sub(r"<[^>]+>", " ", html or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:5000]  # GMC description limit

def size_from_option(variant):
    """Extract size from variant options."""
    for opt in ["option1", "option2", "option3"]:
        val = variant.get(opt, "") or ""
        if val.upper() in ("XS","S","M","L","XL","XXL","2XL","3XL","XXXL",
                            "ONE SIZE","OS","FREE SIZE"):
            return val
        if re.match(r"^\d{1,2}$", val):   # numeric sizes
            return val
    return None

def color_from_tags(tags_str):
    """Try to extract a color from product tags."""
    colors = ["black","white","grey","gray","navy","red","blue","green",
              "brown","tan","cream","khaki","olive","purple","pink","orange","yellow"]
    for tag in (tags_str or "").lower().split(","):
        tag = tag.strip()
        for c in colors:
            if c in tag:
                return c.title()
    return None

# Google Product Category for apparel
APPAREL_CATEGORY = "Apparel & Accessories > Clothing"
ACCESSORIES_CATEGORY = "Apparel & Accessories"

def category_for(product_type, tags):
    pt = (product_type or "").lower()
    tg = (tags or "").lower()
    if any(w in pt or w in tg for w in ["hoodie","sweatshirt","crewneck","zip-up","outerwear","jacket"]):
        return "Apparel & Accessories > Clothing > Activewear > Hoodies & Sweatshirts"
    if any(w in pt or w in tg for w in ["t-shirt","tee","tshirt","top","polo","tank"]):
        return "Apparel & Accessories > Clothing > Shirts & Tops"
    if any(w in pt or w in tg for w in ["short","jogger","pant","set","sweat"]):
        return "Apparel & Accessories > Clothing > Pants"
    if any(w in pt or w in tg for w in ["hat","cap","trucker","beanie"]):
        return "Apparel & Accessories > Clothing Accessories > Hats"
    if any(w in pt or w in tg for w in ["sunglass","glass","eyewear"]):
        return "Apparel & Accessories > Jewelry & Watches > Watch Accessories"
    return APPAREL_CATEGORY

gmc_records = []

for product in all_products:
    pid        = product["id"]
    title      = product["title"]
    handle     = product["handle"]
    body_html  = product.get("body_html", "") or ""
    description = strip_html(body_html) or f"Shop the {title} from Legendary Branding. Premium streetwear crafted for quality and style."
    product_type = product.get("product_type", "") or ""
    tags        = product.get("tags", "") or ""
    images      = product.get("images", [])
    variants    = product.get("variants", [])

    # Primary image
    primary_image = images[0]["src"] if images else ""

    # Build per-variant records
    for variant in variants:
        vid   = variant["id"]
        price = variant.get("price", "0.00")
        avail = "in stock" if (variant.get("inventory_quantity", 1) or 1) > 0 else "out of stock"

        # Variant-specific title
        var_title = variant.get("title", "")
        if var_title and var_title.upper() not in ("DEFAULT TITLE", "DEFAULT"):
            full_title = f"{title} - {var_title}"
        else:
            full_title = title

        # Variant image (use variant image if set, else product primary)
        var_img_id = variant.get("image_id")
        var_image  = primary_image
        if var_img_id:
            for img in images:
                if img["id"] == var_img_id:
                    var_image = img["src"]
                    break

        # Additional images (up to 10 for GMC)
        additional_images = [img["src"] for img in images if img["src"] != var_image][:9]

        size  = size_from_option(variant)
        color = color_from_tags(tags)

        record = {
            "id":                    f"online:en:US:{vid}",
            "offerId":               str(vid),
            "title":                 full_title[:150],
            "description":           description,
            "link":                  f"{STORE_URL}/products/{handle}",
            "imageLink":             var_image,
            "availability":          avail,
            "price":                 {"value": price, "currency": "USD"},
            "brand":                 "Legendary Branding",
            "condition":             "new",
            "googleProductCategory": category_for(product_type, tags),
            "productType":           product_type or "Apparel",
            "identifierExists":      False,   # apparel exemption — no GTIN
            "channel":               "online",
            "contentLanguage":       "en",
            "targetCountry":         "US",
            "ageGroup":              "adult",
            "gender":                "unisex",
            "customLabel0":          "legendary-branding",
            "customLabel1":          (tags.split(",")[0].strip() if tags else ""),
        }

        if additional_images:
            record["additionalImageLinks"] = additional_images

        if size:
            record["sizes"] = [size]
            record["sizeSystem"] = "US"
            record["sizeType"] = "regular"

        if color:
            record["color"] = color

        gmc_records.append(record)

print(f"  Variants to insert: {len(gmc_records)}")

# ── Step 3: Batch insert into GMC ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3: Inserting into Google Merchant Center (batch)")
print("=" * 70)

BATCH_SIZE = 1000  # GMC custombatch limit
inserted   = 0
errors     = 0
error_details = []

for i in range(0, len(gmc_records), BATCH_SIZE):
    batch = gmc_records[i:i + BATCH_SIZE]
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
                error_details.append({
                    "batchId": entry.get("batchId"),
                    "errors":  [e.get("message") for e in errs[:2]],
                })
            else:
                inserted += 1
        print(f"  Batch {i // BATCH_SIZE + 1}: inserted {len(batch)} | running total: {inserted} ok / {errors} err")
    except HttpError as e:
        print(f"  Batch {i // BATCH_SIZE + 1} HTTP error: {e}")
        errors += len(batch)
    time.sleep(1)

print(f"\n  Total inserted: {inserted} | Errors: {errors}")

if error_details:
    print("\n  SAMPLE ERRORS (first 10):")
    for ed in error_details[:10]:
        print(f"    batchId {ed['batchId']}: {ed['errors']}")

print("\n" + "=" * 70)
print("FEED POPULATE COMPLETE")
print("=" * 70)
print(f"  Products:  {len(all_products)}")
print(f"  Variants:  {len(gmc_records)}")
print(f"  Inserted:  {inserted}")
print(f"  Errors:    {errors}")
print("  GMC will review and approve products within 3–72 hours.")
print("  Re-run gmc-audit after 24h to check approval status.")
