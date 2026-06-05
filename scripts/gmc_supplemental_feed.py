#!/usr/bin/env python3
"""
gmc_supplemental_feed.py — Legendary Branding
Apply keyword-optimised title overrides + full apparel attribute enrichment
to all GMC product variants via Content API custombatch insert.

Strategy:
  - Pulls all active Shopify products (live source of truth)
  - Builds optimised titles via rotation engine:
      * 5 keyword prefix variants per category, cycles every 7 days
      * Locks titles with sustained CTR >= 4% for 7+ days (high performers)
      * Unlocks if locked title drops below 2% CTR
      * Rotation state persisted in GCS (lb-feed-state/title_rotation_state.json)
  - Enriches every variant with apparel attributes:
      color, size, gender, age_group, material, size_type, size_system,
      google_product_category, brand, identifier_exists
  - Adds description from Shopify bodyHtml (keyword-rich, plain text)
  - Adds shippingDetails (free shipping per country)
  - Generates records for 5 markets: US, CA, GB, AU, IE
  - Upserts every variant × every market in GMC using custombatch insert
  - Safe, non-destructive — only touches feed-level product records

Auth:     GCP service account (GCP_SA_KEY secret)
Merchant: 582171114

Organic impact:
  - Unlocks Google Popular Products carousel (apparel/accessories, mobile US)
  - Qualifies for AI Mode Shopping Graph constrained-query matching
  - Resolves GTIN-suppression (identifier_exists: false signals intentional)
  - Upgrades free listing Merchant Listing rich results
  - Title rotation surfaces fresh keyword variants to Google's relevance model
"""
import os, json, time, re, html, requests, httplib2
import google_auth_httplib2
from datetime import date
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from title_rotation_module import (
    load_state, save_state,
    fetch_free_listing_performance,
    get_rotated_prefix,
)

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
    if "boxy fit" in tg:                           return "Boxy Fit"
    if "cropped" in tg:                            return "Cropped"
    if "loose fit" in tg:                          return "Loose Fit"
    if "regular fit" in tg:                        return "Regular Fit"
    if "baggy" in tg:                              return "Baggy Fit"
    if "wide-leg" in tg or "wide leg" in tg:       return "Wide Leg"
    if "oversized fit" in tg or "oversized" in tg: return "Oversized Fit"
    return "Oversized Fit"

def get_gsm(tags_list):
    for tag in tags_list:
        if "GSM" in tag:
            return tag.strip()
    return ""

# ── Description optimisation ────────────────────────────────────────────────

def strip_html(raw_html):
    """Strip all HTML tags, remove size tables, decode entities to plain text."""
    if not raw_html:
        return ""
    text = re.sub(r'<table[\s\S]*?</table>', '', raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def build_optimised_description(body_html, material=None, fit=None, color=None):
    """
    Build a keyword-rich plain-text GMC description from Shopify bodyHtml.

    Extracts the intro pitch, Features, and Fabric & Construction sections,
    then appends variant-level signals (material weight, fit, color).
    Target: 500-800 chars. Hard limit: 5,000 chars (GMC max).
    """
    plain = strip_html(body_html)
    parts = []

    # Intro / pitch paragraph
    intro_match = re.search(
        r'(?:Premium Streetwear|Streetwear)[,.]?\s+(.+?)(?=Features|Fabric)',
        plain, re.IGNORECASE | re.DOTALL
    )
    if intro_match:
        intro = re.sub(r'\s+', ' ', intro_match.group(0)).strip()
        intro = re.sub(r'^.*?(?:Premium Streetwear[,.]?\s*)', '', intro, flags=re.IGNORECASE).strip()
        if intro:
            parts.append(intro[:250])

    # Features section
    features_match = re.search(
        r'Features\s+([\s\S]+?)(?=Fabric|Construction|Care Instructions|Size Guide|Shipping)',
        plain, re.IGNORECASE
    )
    if features_match:
        features = re.sub(r'\s+', ' ', features_match.group(1)).strip()
        if features:
            parts.append(f"Features: {features[:200]}")

    # Fabric & Construction section
    fabric_match = re.search(
        r'Fabric\s*&?\s*Construction\s+([\s\S]+?)(?=Care Instructions|Size Guide|Shipping)',
        plain, re.IGNORECASE
    )
    if fabric_match:
        fabric = re.sub(r'\s+', ' ', fabric_match.group(1)).strip()
        if fabric:
            parts.append(f"Construction: {fabric[:200]}")

    # Material/weight signal from enrichment
    if material:
        parts.append(f"Fabric: {material}.")

    # Variant-level signals
    attr_parts = []
    if fit:
        attr_parts.append(fit)
    if color:
        attr_parts.append(f"available in {color}")
    if attr_parts:
        parts.append("Offered in " + ", ".join(attr_parts) + ".")

    # Fallback for products with no bodyHtml
    if not parts:
        base = "Premium streetwear apparel by Legendary Branding."
        if material:
            base += f" {material}."
        if fit:
            base += f" {fit}."
        parts.append(base)

    description = re.sub(r'\s+', ' ', " ".join(parts)).strip()
    description = html.unescape(description)
    return description[:5000]


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


# ── Apparel attribute enrichment helpers ─────────────────────────────────────

# GSM tag → (material description, weight label for AI Mode)
GSM_MATERIAL_MAP = {
    "190GSM": "100% Cotton 190GSM Lightweight Jersey",
    "235GSM": "100% Cotton 235GSM Heavyweight Cotton Jersey",
    "250GSM": "100% Cotton 250GSM Heavyweight Cotton Jersey",
    "280GSM": "100% Cotton 280GSM Heavyweight Cotton Jersey",
    "285GSM": "100% Cotton 285GSM Heavyweight Cotton Jersey",
    "380GSM": "80% Cotton 20% Polyester 380GSM Heavyweight Fleece",
    "400GSM": "80% Cotton 20% Polyester 400GSM Premium Fleece",
    "440GSM": "80% Cotton 20% Polyester 440GSM Premium Heavyweight Fleece",
    "460GSM": "80% Cotton 20% Polyester 460GSM Ultra Heavyweight Fleece",
}

def get_material(tags_list):
    """Derive material string from GSM or fabric tags."""
    tg = " ".join(tags_list)
    # Check GSM tags first (most specific)
    for gsm_key, material in GSM_MATERIAL_MAP.items():
        if gsm_key in tg:
            return material
    # Fallback fabric tags
    tg_lower = tg.lower()
    if "denim" in tg_lower:
        return "100% Cotton Denim"
    if "premium fleece" in tg_lower:
        return "80% Cotton 20% Polyester Premium Fleece"
    if "100% cotton" in tg_lower:
        return "100% Cotton"
    return "Cotton Blend"

def get_gender(tags_list, option3=None):
    """Derive gender from tags or variant option3."""
    if option3:
        o3 = option3.lower()
        if "women" in o3 or "female" in o3:
            return "female"
        if "men" in o3 and "women" not in o3:
            return "male"
    tg = " ".join(tags_list).lower()
    if "women" in tg and "mens" not in tg:
        return "female"
    if "men's streetwear" in tg:
        return "male"
    return "unisex"

def get_size_type(tags_list, product_title):
    """Derive size_type from fit tags — maps to Google's allowed values."""
    tg  = " ".join(tags_list).lower()
    ttl = product_title.lower()
    if "plus" in tg or "plus" in ttl:
        return "plus"
    if "petite" in tg or "petite" in ttl:
        return "petite"
    if "tall" in tg or "tall" in ttl:
        return "tall"
    # Oversized/boxy/baggy/cropped all map to regular in Google's taxonomy
    # (Google size_type: regular, petite, plus, tall, maternity, big and tall)
    return "regular"

def normalize_color(raw_color):
    """
    Normalize color values to simple Google-friendly names.
    Google prefers: Black, White, Gray, Red, Blue, etc. — not "Charcoal Grey"
    Keeps max 3 colors, comma-separated not supported by single color field.
    Returns the dominant simplified color.
    """
    if not raw_color:
        return None
    # If the "color" field is actually a size (data inconsistency in some products)
    size_values = {"XS","S","M","L","XL","2XL","3XL","4XL","5XL","XXL","XXXL"}
    if raw_color.strip().upper() in size_values:
        return None
    COLOR_NORMALIZE = {
        "charcoal gray": "Gray", "charcoal grey": "Gray", "charcoal": "Gray",
        "dark gray": "Gray",     "dark grey": "Gray",     "heather gray": "Gray",
        "graphite": "Gray",      "carbon gray": "Gray",   "dust": "Gray",
        "dark green": "Green",   "military green": "Green","olive green": "Olive",
        "grass green": "Green",  "medium jungle green": "Green",
        "grayish green": "Green","dark army green": "Green",
        "navy blue": "Navy",     "collegiate navy": "Navy","midnight": "Navy",
        "royal blue": "Blue",    "collegiate royal": "Blue","haze blue": "Blue",
        "dusty blue": "Blue",    "hyacinth blue": "Blue", "cow blue": "Blue",
        "grayish blue": "Blue",  "sky blue": "Blue",      "denim blue": "Blue",
        "pastell blue": "Blue",
        "light blue": "Light Blue",
        "dark blue": "Blue",
        "rose pink": "Pink",     "dark pink": "Pink",     "watermelon pink": "Pink",
        "pink candy": "Pink",    "rose red": "Red",       "garnet red": "Red",
        "garnet": "Red",         "scarlet": "Red",        "burgundy": "Burgundy",
        "maroon": "Maroon",      "raspberry purple": "Purple",
        "rose": "Pink",
        "off-white": "White",    "ivory": "White",        "ecru": "Cream",
        "cream": "Cream",
        "athletic heather": "Gray",
        "sand apricot": "Beige", "apricot": "Beige",      "taupe": "Beige",
        "khaki": "Khaki",
        "safety green": "Green",
        "americano": "Brown",    "coffee": "Brown",
        "dark yellow": "Yellow",
    }
    lower = raw_color.lower().strip()
    return COLOR_NORMALIZE.get(lower, raw_color.title())

def normalize_size(raw_size):
    """Normalize size values; return None if it looks like a color."""
    if not raw_size:
        return None
    # If option2 looks like a color name (some products swap options), skip
    known_colors = {
        "black","white","red","blue","green","yellow","pink","purple",
        "grey","gray","navy","brown","orange","beige","cream","ivory",
        "olive","maroon","teal","coral","salmon","tan",
    }
    if raw_size.lower() in known_colors:
        return None
    # Strip parenthetical numeric sizes used in pants/jeans e.g. "L (31)"
    cleaned = re.sub(r'\s*\(\d+\)', '', raw_size).strip()
    # Normalize XXL variants
    SIZE_NORMALIZE = {
        "xxl": "XXL", "xxxl": "3XL",
        "xs": "XS", "s": "S", "m": "M", "l": "L",
        "xl": "XL", "2xl": "2XL", "3xl": "3XL",
        "4xl": "4XL", "5xl": "5XL",
    }
    return SIZE_NORMALIZE.get(cleaned.lower(), cleaned)

def get_google_category_id(product_type):
    """
    Map Shopify product_type to Google product taxonomy numeric IDs.
    Using Google taxonomy v1 IDs for Apparel & Accessories.
    """
    CATEGORY_MAP = {
        "Apparel & Accessories > Clothing > Shirts & Tops":              "212",
        "Apparel & Accessories > Clothing > Activewear > Hoodies":       "5322",
        "Apparel & Accessories > Clothing > Pants":                      "207",
        "Apparel & Accessories > Clothing > Shorts":                     "214",
        "Apparel & Accessories > Clothing > Outerwear":                  "5441",
        "Apparel & Accessories > Clothing > Outfit Sets":                "1604",
        "Apparel & Accessories > Clothing Accessories > Hats":           "178",
    }
    return CATEGORY_MAP.get(product_type, "1604")  # default: Apparel & Accessories > Clothing


# ── Target markets ───────────────────────────────────────────────────────────
# Each entry generates a full set of feed records in GMC for that country.
# All ship from the same Shopify store (Printful fulfillment, worldwide).
# Shopify Markets handles local currency presentation at checkout.
# Content API product ID format: online:{lang}:{country}:{variant_id}
TARGET_MARKETS = [
    {"country": "US", "lang": "en", "currency": "USD", "size_system": "US"},
    {"country": "CA", "lang": "en", "currency": "USD", "size_system": "US"},
    {"country": "GB", "lang": "en", "currency": "USD", "size_system": "UK"},
    {"country": "AU", "lang": "en", "currency": "USD", "size_system": "AU"},
    {"country": "IE", "lang": "en", "currency": "USD", "size_system": "EU"},
]

def build_shipping(country: str) -> list:
    """Return free shipping entry for a given country code."""
    return [{
        "country": country,
        "service": "Standard Shipping",
        "price": {"value": "0.00", "currency": "USD"},
    }]


# ── Step 1: Pull all active Shopify products ──────────────────────────────────
print("\n" + "=" * 70)
print("STEP 1: Fetching active Shopify products")
print("=" * 70)

all_products = []
url    = f"https://{SHOP}/admin/api/{API_VERSION}/products.json"
params = {
    "limit":  250,
    "status": "active",
    "fields": "id,title,handle,product_type,tags,body_html,variants,images",
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


# ── Step 2: Build enriched records per variant ───────────────────────────────
print("\n" + "=" * 70)
print("STEP 1b: Loading rotation state + GMC performance data")
print("=" * 70)

TODAY = date.today().isoformat()
rotation_state = load_state(SA_KEY_JSON)
perf_data      = fetch_free_listing_performance(SA_KEY_JSON)

print(f"  Today          : {TODAY}")
print(f"  Products tracked in state: {len(rotation_state.get('products', {}))}")
print(f"  Offer IDs with performance data: {len(perf_data)}")

print("\n" + "=" * 70)
print("STEP 2: Building enriched variant records")
print("=" * 70)

records = []

for product in all_products:
    title        = product["title"]
    handle       = product["handle"]
    tags_raw     = product.get("tags", "") or ""
    tags_list    = [t.strip() for t in tags_raw.split(",") if t.strip()]
    images       = product.get("images", [])
    primary_image = images[0]["src"] if images else ""
    product_type  = product.get("product_type", "") or ""

    cat          = categorize(title, tags_list)
    gsm          = get_gsm(tags_list)
    fit          = get_fit(tags_list)
    material     = get_material(tags_list)
    google_cat   = get_google_category_id(product_type)
    body_html    = product.get("body_html", "") or ""
    variants_raw = product.get("variants", [])

    # ── Rotation-aware prefix selection ───────────────────────────────────────
    rot_prefix, rot_reason = get_rotated_prefix(
        handle, cat, variants_raw, perf_data, rotation_state, TODAY, gsm=gsm
    )

    # Build optimised title using rotation prefix
    def build_rotated_title(product_title, tags_list):
        opt = f"{rot_prefix} | {product_title} — {fit}"
        return opt[:150] if len(opt) <= 150 else opt[:147].rstrip() + "..."

    opt_title    = build_rotated_title(title, tags_list)

    for variant in product.get("variants", []):
        vid       = variant["id"]
        price     = variant.get("price", "0.00")
        inventory = variant.get("inventory_quantity", 1) or 0
        avail     = "in stock" if inventory > 0 else "out of stock"

        # Extract variant options
        raw_opt1 = variant.get("option1") or ""   # typically Color
        raw_opt2 = variant.get("option2") or ""   # typically Size
        raw_opt3 = variant.get("option3") or ""   # sometimes Gender/Unisex

        # Normalize
        color     = normalize_color(raw_opt1)
        size      = normalize_size(raw_opt2)
        # Some products have size in option1 and no color — detect and swap
        if not color and raw_opt1:
            maybe_size = normalize_size(raw_opt1)
            if maybe_size:
                size  = maybe_size
                color = None

        gender    = get_gender(tags_list, raw_opt3 or None)
        size_type = get_size_type(tags_list, title)

        # Variant-level display title
        var_title = variant.get("title", "") or ""
        if var_title.upper() not in ("DEFAULT TITLE", "DEFAULT", ""):
            display_title = f"{opt_title} - {var_title}"
        else:
            display_title = opt_title
        display_title = display_title[:150]

        # Variant image
        var_img_id = variant.get("image_id")
        var_image  = primary_image
        if var_img_id:
            for img in images:
                if img["id"] == var_img_id:
                    var_image = img["src"]
                    break

        description = build_optimised_description(
            body_html,
            material=material,
            fit=fit,
            color=color if color else None,
        )

        # ── Generate one record per target market ────────────────────────
        for market in TARGET_MARKETS:
            mcc  = market["country"]
            lang = market["lang"]
            cur  = market["currency"]
            ss   = market["size_system"]

            record = {
                # ── Core required fields ──────────────────────────────────
                "id":               f"online:{lang}:{mcc}:{vid}",
                "offerId":          str(vid),
                "title":            display_title,
                "description":      description,
                "link":             f"{STORE_URL}/products/{handle}",
                "imageLink":        var_image,
                "availability":     avail,
                "price":            {"value": price, "currency": cur},
                "condition":        "new",
                "channel":          "online",
                "contentLanguage":  lang,
                "targetCountry":    mcc,

                # ── Brand & identifier ─────────────────────────────────────
                "brand":            "Legendary Branding",
                "identifierExists": False,

                # ── Google category ────────────────────────────────────────
                "googleProductCategory": google_cat,

                # ── Apparel attributes ─────────────────────────────────────
                "gender":           gender,
                "ageGroup":         "adult",
                "sizeSystem":       ss,
                "sizeType":         size_type,

                # ── Shipping (free, per country) ───────────────────────────
                "shipping":         build_shipping(mcc),
            }

            # Only add color/size/material if we have valid values
            if color:
                record["color"]    = color
            if size:
                record["sizes"]    = [size]
            if material:
                record["material"] = material

            records.append(record)

# Save updated rotation state back to GCS
print("\n" + "=" * 70)
print("STEP 2b: Saving rotation state")
print("=" * 70)
rotation_state["last_run"] = TODAY
try:
    save_state(rotation_state, SA_KEY_JSON)
except Exception as e:
    print(f"  WARNING: Could not save rotation state: {e}")
    print("  Feed will continue — state will be recalculated next run")

# Rotation summary log
locked_count  = sum(1 for p in rotation_state["products"].values() if p.get("locked"))
rotated_today = sum(
    1 for p in rotation_state["products"].values()
    if p.get("last_rotated") == TODAY
)
print(f"  Products locked (high performers) : {locked_count}")
print(f"  Products rotated today            : {rotated_today}")
print(f"  Products in cooling period        : {len(rotation_state['products']) - locked_count - rotated_today}")

print(f"  Variant records built: {len(records)}")

# Attribute coverage report
has_color    = sum(1 for r in records if r.get("color"))
has_size     = sum(1 for r in records if r.get("sizes"))
has_material = sum(1 for r in records if r.get("material"))
has_desc     = sum(1 for r in records if r.get("description"))
avg_desc_len = int(sum(len(r.get("description", "")) for r in records) / max(len(records), 1))
markets_covered = len(TARGET_MARKETS)
print(f"\n  MARKETS: {markets_covered} ({', '.join(m['country'] for m in TARGET_MARKETS)})")
print(f"  ATTRIBUTE COVERAGE (across all markets):")
print(f"    description: {has_desc}/{len(records)} records ({has_desc*100//len(records)}%) — avg {avg_desc_len} chars")
print(f"    color    : {has_color}/{len(records)} variants ({has_color*100//len(records)}%)")
print(f"    size     : {has_size}/{len(records)} variants ({has_size*100//len(records)}%)")
print(f"    material : {has_material}/{len(records)} variants ({has_material*100//len(records)}%)")
print(f"    gender   : {len(records)}/{len(records)} variants (100%)")
print(f"    age_group: {len(records)}/{len(records)} variants (100%)")
print(f"    brand    : {len(records)}/{len(records)} variants (100%)")
print(f"    id_exists: {len(records)}/{len(records)} variants (100% — set to false)")
print(f"    shipping : {len(records)}/{len(records)} variants (100%)")

# Preview
print("\n  TITLE PREVIEW (first 5 unique products):")
seen = set()
count = 0
for r in records:
    base = r["title"].split(" - ")[0]
    if base not in seen:
        seen.add(base)
        extra = []
        if r.get("color"):    extra.append(f"color={r['color']}")
        if r.get("sizes"):    extra.append(f"size={r['sizes'][0]}")
        if r.get("material"): extra.append(f"material={r['material'][:30]}...")
        print(f"    TITLE   : {r['title'][:100]}")
        print(f"    ATTRS   : gender={r['gender']} | {' | '.join(extra)}")
        print()
        count += 1
    if count >= 5:
        break


# ── Step 3: Batch upsert into GMC ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3: Upserting into Google Merchant Center")
print("=" * 70)

BATCH_SIZE   = 1000
inserted     = 0
errors       = 0
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
    batch_num = i // BATCH_SIZE + 1
    max_retries = 4
    for attempt in range(1, max_retries + 1):
        try:
            http = google_auth_httplib2.AuthorizedHttp(
                creds, http=httplib2.Http(timeout=120)
            )
            resp = service.products().custombatch(body={"entries": entries}).execute(num_retries=2, http=http)
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
            print(f"  Batch {batch_num}: {len(batch)} records | {inserted} ok / {errors} err")
            break  # success — exit retry loop
        except HttpError as e:
            print(f"  Batch {batch_num} HTTP error (attempt {attempt}/{max_retries}): {e}")
            if attempt == max_retries:
                errors += len(batch)
            else:
                time.sleep(2 ** attempt)  # 2s, 4s, 8s backoff
        except Exception as e:
            print(f"  Batch {batch_num} error (attempt {attempt}/{max_retries}): {e}")
            if attempt == max_retries:
                errors += len(batch)
            else:
                time.sleep(2 ** attempt)
    time.sleep(1)


# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUPPLEMENTAL FEED + ATTRIBUTE ENRICHMENT COMPLETE")
print("=" * 70)
print(f"  Products processed  : {len(all_products)}")
print(f"  Variants upserted   : {inserted}")
print(f"  Errors              : {errors}")
if error_sample:
    print("\n  SAMPLE ERRORS:")
    for es in error_sample:
        print(f"    [{es['batchId']}] {es['errors']}")
print()
print("  Attributes applied per variant:")
print("    title, brand, identifierExists=false, googleProductCategory")
print("    gender, ageGroup, sizeSystem=US, sizeType")
print("    color, sizes, material (where derivable from Shopify tags/options)")
print("    shipping (free US)")
print()
print("  Organic surfaces now eligible for:")
print("    - Google Popular Products carousel (apparel, mobile US)")
print("    - AI Mode Shopping Graph constrained-query matching")
print("    - Full Merchant Listing rich results")
print("    - Google Lens visual search product matching")
print("  Titles propagate to Shopping surfaces within 24-48h.")
print("  Run gmc-audit after 24h to verify no new disapprovals.")
