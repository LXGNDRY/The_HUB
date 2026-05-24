#!/usr/bin/env python3
"""
gmc_feed_patch.py — Legendary Branding
Patch all 1,181 GMC variants to fix:
  1. google_category_unrecognized  → use official numeric taxonomy IDs
  2. missing_item_attribute_for_product_type → add size, color, gender properly
  3. MPN → set to variant SKU or generated value (reduces data quality warnings)

Google Product Taxonomy numeric IDs (official):
  5322  = Apparel & Accessories > Clothing > Activewear > Hoodies & Sweatshirts
  212   = Apparel & Accessories > Clothing > Shirts & Tops
  3455  = Apparel & Accessories > Clothing > Pants (covers shorts/joggers)
  2271  = Apparel & Accessories > Clothing > Outerwear > Coats & Jackets
  178   = Apparel & Accessories > Clothing Accessories > Hats
  301   = Apparel & Accessories > Sunglasses
  5598  = Apparel & Accessories > Clothing > Polos
  2132  = Apparel & Accessories > Clothing > Sets
  1604  = Apparel & Accessories > Clothing > Tank Tops & Sleeveless Shirts
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

print("Fetching fresh Shopify token...")
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

# ── Google Taxonomy IDs ───────────────────────────────────────────────────────
# Using numeric IDs — these are stable and unambiguous
CATEGORY_MAP = {
    "hoodie":      5322,   # Hoodies & Sweatshirts
    "sweatshirt":  5322,
    "crewneck":    5322,
    "zip-up":      5322,
    "fleece":      5322,
    "jacket":      2271,   # Coats & Jackets
    "coat":        2271,
    "outerwear":   2271,
    "polo":        5598,   # Polos
    "t-shirt":     212,    # Shirts & Tops
    "tshirt":      212,
    "tee":         212,
    "top":         212,
    "tank":        1604,   # Tank Tops & Sleeveless
    "set":         2132,   # Sets
    "jogger":      3455,   # Pants
    "short":       3455,
    "pant":        3455,
    "hat":         178,    # Hats
    "cap":         178,
    "trucker":     178,
    "beanie":      178,
    "sunglass":    301,    # Sunglasses
    "eyewear":     301,
}
DEFAULT_CATEGORY = 1604  # fallback: Shirts & Tops (most common)

def get_category_id(product_type, tags, title):
    combined = " ".join([
        (product_type or "").lower(),
        (tags or "").lower(),
        (title or "").lower(),
    ])
    for keyword, cat_id in CATEGORY_MAP.items():
        if keyword in combined:
            return cat_id
    return DEFAULT_CATEGORY

# ── Size extraction — comprehensive ──────────────────────────────────────────
KNOWN_SIZES = {
    "xs", "s", "m", "l", "xl", "xxl", "2xl", "3xl", "xxxl",
    "xsmall", "small", "medium", "large", "x-large", "xx-large",
    "one size", "os", "free size", "one-size",
    "28", "30", "32", "34", "36", "38", "40",  # numeric
}

def extract_size(variant):
    """Pull size from variant options, title, or SKU."""
    for opt_key in ["option1", "option2", "option3"]:
        val = (variant.get(opt_key) or "").strip()
        if val.lower() in KNOWN_SIZES:
            return val.upper() if len(val) <= 5 else val.title()
    # Try variant title
    title = (variant.get("title") or "").upper()
    for sz in ["XS","S","M","L","XL","XXL","2XL","3XL","XXXL","ONE SIZE","OS"]:
        if re.search(rf'\b{re.escape(sz)}\b', title):
            return sz
    return "One Size"   # default for accessories / no-size items

# ── Color extraction — from options first, then tags ─────────────────────────
COLOR_WORDS = [
    "black","white","grey","gray","navy","red","blue","green","brown","tan",
    "cream","khaki","olive","purple","pink","orange","yellow","beige","maroon",
    "teal","coral","gold","silver","charcoal","off-white","offwhite",
    "heather","vintage","washed","snow","tie-dye","camo","multi",
]

def extract_color(variant, tags_str, title):
    # Option fields first
    for opt_key in ["option1", "option2", "option3"]:
        val = (variant.get(opt_key) or "").lower().strip()
        for c in COLOR_WORDS:
            if c in val:
                return val.title()
    # Tags
    for tag in (tags_str or "").lower().split(","):
        tag = tag.strip()
        for c in COLOR_WORDS:
            if c == tag or tag.startswith(c):
                return tag.title()
    # Title
    for c in COLOR_WORDS:
        if c in (title or "").lower():
            return c.title()
    return "Black"   # safe default for streetwear

# ── Step 1: Pull all active Shopify products ──────────────────────────────────
print("\n" + "=" * 70)
print("STEP 1: Fetching Shopify products")
print("=" * 70)

all_products = []
url    = f"https://{SHOP}/admin/api/{API_VERSION}/products.json"
params = {
    "limit":  250,
    "status": "active",
    "fields": "id,title,body_html,handle,product_type,tags,variants,images,vendor,options",
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

print(f"  Products fetched: {len(all_products)}")

# ── Step 2: Pull current GMC feed ────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 2: Pulling current GMC feed")
print("=" * 70)

all_gmc = []
req = service.products().list(merchantId=MERCHANT_ID, maxResults=250)
while req:
    res = req.execute()
    all_gmc.extend(res.get("resources", []))
    req = service.products().list_next(req, res)

print(f"  GMC products found: {len(all_gmc)}")

# Build variant lookup: variant_id → full product + variant data
variant_lookup = {}
for product in all_products:
    images = product.get("images", [])
    primary_image = images[0]["src"] if images else ""
    for variant in product.get("variants", []):
        variant_lookup[str(variant["id"])] = {
            "product":  product,
            "variant":  variant,
            "primary_image": primary_image,
            "images":   images,
        }

# ── Step 3: Build patch entries ───────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3: Building patch records")
print("=" * 70)

BATCH_SIZE = 1000
patch_entries_all = []
skipped = 0

for gmc_product in all_gmc:
    gmc_id = gmc_product.get("id", "")
    # Extract variant ID from GMC product ID: online:en:US:{variant_id}
    match = re.search(r":(\d{10,})$", gmc_id)
    if not match:
        skipped += 1
        continue
    vid = match.group(1)
    lookup = variant_lookup.get(vid)
    if not lookup:
        skipped += 1
        continue

    product      = lookup["product"]
    variant      = lookup["variant"]
    primary_img  = lookup["primary_image"]
    images       = lookup["images"]
    title        = product["title"]
    product_type = product.get("product_type", "") or ""
    tags         = product.get("tags", "") or ""

    # Variant-specific title
    var_title = variant.get("title", "") or ""
    if var_title.upper() not in ("DEFAULT TITLE", "DEFAULT", ""):
        full_title = f"{title} - {var_title}"
    else:
        full_title = title

    # Variant image
    var_img_id = variant.get("image_id")
    var_image  = primary_img
    if var_img_id:
        for img in images:
            if img["id"] == var_img_id:
                var_image = img["src"]
                break

    additional_images = [img["src"] for img in images if img["src"] != var_image][:9]

    size  = extract_size(variant)
    color = extract_color(variant, tags, title)
    cat_id = get_category_id(product_type, tags, title)

    # MPN: use SKU if available, else generate from variant ID
    sku = (variant.get("sku") or "").strip()
    mpn = sku if sku else f"LB-{vid}"

    patched = dict(gmc_product)
    patched.update({
        "googleProductCategory": str(cat_id),
        "sizes":                 [size],
        "sizeSystem":            "US",
        "sizeType":              "regular",
        "color":                 color,
        "gender":                "unisex",
        "ageGroup":              "adult",
        "brand":                 "Legendary Branding",
        "identifierExists":      False,
        "mpn":                   mpn,
        "condition":             "new",
    })

    if additional_images:
        patched["additionalImageLinks"] = additional_images

    patch_entries_all.append({
        "batchId":    len(patch_entries_all),
        "merchantId": MERCHANT_ID,
        "method":     "insert",   # insert = upsert in Content API
        "product":    patched,
    })

print(f"  Patch records built: {len(patch_entries_all)}")
print(f"  Skipped (no match):  {skipped}")

# ── Step 4: Batch upsert ─────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 4: Patching GMC feed (batch upsert)")
print("=" * 70)

updated     = 0
errors      = 0
error_sample = []

for i in range(0, len(patch_entries_all), BATCH_SIZE):
    batch = patch_entries_all[i:i + BATCH_SIZE]
    # Reset batchIds within each batch (must be unique within a single request)
    for idx, entry in enumerate(batch):
        entry["batchId"] = idx
    try:
        resp = service.products().custombatch(body={"entries": batch}).execute()
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
                updated += 1
        print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} records | running: {updated} ok / {errors} err")
    except HttpError as e:
        print(f"  Batch {i // BATCH_SIZE + 1} HTTP error: {e}")
        errors += len(batch)
    time.sleep(1)

print(f"\n  Total updated: {updated} | Errors: {errors}")
if error_sample:
    print("\n  SAMPLE ERRORS:")
    for es in error_sample:
        print(f"    [{es['batchId']}] {es['errors']}")

print("\n" + "=" * 70)
print("PATCH COMPLETE")
print("=" * 70)
print(f"  GMC products patched: {updated}")
print(f"  Errors:               {errors}")
print(f"  Fixes applied:")
print(f"    - googleProductCategory: numeric taxonomy IDs")
print(f"    - sizes: extracted from variant options")
print(f"    - color: extracted from options/tags/title")
print(f"    - mpn: SKU or generated LB-{{variant_id}}")
print(f"    - gender + ageGroup: set on all records")
print("  Re-run gmc-audit in 24h to verify issue clearance.")
