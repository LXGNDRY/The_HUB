#!/usr/bin/env python3
"""
gmc_supplemental_feed.py — Legendary Branding
Apply keyword-optimised title overrides + full apparel attribute enrichment
to all GMC product variants via Content API custombatch insert.

IMPROVEMENTS v2:
  1. TARGET_MARKETS expanded to all 63 ad-targeted countries (was 58) — added IN, VN, BR, NG, KE
  2. itemGroupId added per product — groups variants under one Shopping listing
  3. Color normalization expanded — covers all catalog colors
  4. sizeType "oversize" used for oversized/boxy/baggy fits
  5. HK size system corrected to UK (was US)
  6. Portugal (PT) added to TARGET_MARKETS
  7. Change detection — only upserts variants where Shopify updated_at changed
  8. Rotation fallback title on GCS failure — feed never fails silently
  9. age_group tag-driven with adult default (future-proof)

Auth:     GCP service account (GCP_SA_KEY secret)
Merchant: 582171114
Cron:     1:00 AM CST daily
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
SHOPIFY_ADMIN_TOKEN   = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
SHOPIFY_CLIENT_ID     = os.environ.get("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
MERCHANT_ID           = "582171114"
SHOP                  = "lngndny.myshopify.com"
STORE_URL             = "https://legendary-branding.com"
API_VERSION           = "2026-04"

if SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET:
    # Generate a fresh token via Client Credentials Grant every run — matches
    # modules/shopify.py, which sends this as a JSON body (not form-encoded).
    # The old `data={...}` form-encoded version of this call was silently
    # getting rejected with 400 by Shopify for this app.
    print("Fetching fresh Shopify Admin API token...")
    token_resp = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        json={
            "grant_type":    "client_credentials",
            "client_id":     SHOPIFY_CLIENT_ID,
            "client_secret": SHOPIFY_CLIENT_SECRET,
        },
        timeout=15,
    )
    token_resp.raise_for_status()
    SHOPIFY_TOKEN = token_resp.json()["access_token"]
elif SHOPIFY_ADMIN_TOKEN:
    print("SHOPIFY_CLIENT_ID/SECRET not set — using SHOPIFY_ADMIN_TOKEN from env.")
    SHOPIFY_TOKEN = SHOPIFY_ADMIN_TOKEN
else:
    raise RuntimeError("Set SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET, or SHOPIFY_ADMIN_TOKEN.")
SHOPIFY_HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}

creds = service_account.Credentials.from_service_account_info(
    json.loads(SA_KEY_JSON),
    scopes=["https://www.googleapis.com/auth/content"],
)
service = build("content", "v2.1", credentials=creds)


# ── Categorisation helpers ────────────────────────────────────────────────────

def categorize(title, tags_list):
    t  = title.lower()
    tg = " ".join(tags_list).lower()
    if "hoodie" in t:                                     return "hoodie"
    if "crewneck sweatshirt" in t:                        return "crewneck"
    if "crewneck" in t and "sweatshirt" in t:             return "crewneck"
    if "sweatshirt" in t:                                 return "sweatshirt"
    if "sweatpants" in t:                                 return "sweatpants"
    if "wide-leg" in t and ("pant" in t or "sweat" in t): return "sweatpants"
    if "flare sweatpants" in t:                           return "sweatpants"
    if "multi-pocket jean" in t:                          return "jeans"
    if "wide-leg denim" in t:                             return "jeans"
    if "jeans" in t or ("denim" in t and "jean" in t):    return "jeans"
    if "denim t-shirt" in t:                              return "tshirt"
    if "shorts" in t or "short" in t:                     return "shorts"
    if "polo" in t:                                       return "polo"
    if "tank top" in t or "tank" in t:                    return "tank"
    if "jacket" in t or "zip-up" in t:                    return "jacket"
    if "hoodie & jogger set" in t:                        return "set"
    if "set" in t and "hoodie" in t:                      return "set"
    if "trucker hat" in t:                                return "hat"
    if "hat" in t:                                        return "hat"
    return "tshirt"

def get_fit(tags_list):
    tg = " ".join(tags_list).lower()
    if "boxy fit" in tg:                            return "Boxy Fit"
    if "cropped" in tg:                             return "Cropped"
    if "loose fit" in tg:                           return "Loose Fit"
    if "regular fit" in tg:                         return "Regular Fit"
    if "baggy" in tg:                               return "Baggy Fit"
    if "wide-leg" in tg or "wide leg" in tg:        return "Wide Leg"
    if "oversized fit" in tg or "oversized" in tg:  return "Oversized Fit"
    return "Oversized Fit"

def get_gsm(tags_list):
    for tag in tags_list:
        if "GSM" in tag:
            return tag.strip()
    return ""

# ── FIX 9: age_group tag-driven with adult default ────────────────────────────
def get_age_group(tags_list):
    tg = " ".join(tags_list).lower()
    if "youth" in tg or "kids" in tg or "children" in tg:
        return "kids"
    return "adult"

# ── FIX 4: sizeType — oversize for oversized/boxy/baggy ──────────────────────
def get_size_type(tags_list, product_title):
    tg  = " ".join(tags_list).lower()
    ttl = product_title.lower()
    if "plus" in tg or "plus" in ttl:
        return "plus"
    if "petite" in tg or "petite" in ttl:
        return "petite"
    if "tall" in tg or "tall" in ttl:
        return "tall"
    # FIX: oversized/boxy/baggy/cropped → oversize (valid Google value)
    if any(k in tg for k in ("oversized", "boxy", "baggy", "oversize")):
        return "oversize"
    if any(k in ttl for k in ("oversized", "boxy", "baggy")):
        return "oversize"
    return "regular"


# ── Description templates ─────────────────────────────────────────────────────

DESC_TEMPLATES = {
    "tshirt": (
        "{title} — a heavyweight oversized graphic tee built for everyday streetwear. "
        "{gsm_line}"
        "Drop-shoulder cut with a boxy, relaxed silhouette that sits off the shoulder for that authentic streetwear fit. "
        "{fit_line}"
        "Side-seamed construction for shape retention. Pre-shrunk and finished to true-to-size. "
        "100% cotton or cotton-blend fabric — breathable, durable, and wash-resistant. "
        "{color_line}"
        "Machine wash cold. Free shipping. "
        "Perfect for graphic tee collectors, streetwear enthusiasts, and anyone who wants a statement piece that holds up."
    ),
    "hoodie": (
        "{title} — a heavyweight oversized hoodie engineered for bold streetwear style and everyday comfort. "
        "{gsm_line}"
        "Features a kangaroo front pocket, ribbed cuffs and hem, and a drop-shoulder silhouette. "
        "{fit_line}"
        "Double-stitched seams for long-term durability. Pre-shrunk to maintain shape after wash. "
        "100% cotton heavyweight fleece — thick, warm, and built to last. "
        "{color_line}"
        "Machine wash cold, tumble dry low. Free shipping. "
        "Ideal for streetwear layering, casual wear, and anyone who lives in their hoodie."
    ),
    "crewneck": (
        "{title} — a heavyweight oversized crewneck sweatshirt with a clean, minimal streetwear silhouette. "
        "{gsm_line}"
        "Ribbed crew neckline, ribbed cuffs and hem. Drop-shoulder fit for a relaxed, modern look. "
        "{fit_line}"
        "Double-stitched for durability. Pre-shrunk for true-to-size fit. "
        "100% cotton heavyweight fleece — dense, structured fabric that holds its shape. "
        "{color_line}"
        "Machine wash cold. Free shipping. "
        "Great for streetwear layering, casual fits, or everyday wear year-round."
    ),
    "sweatshirt": (
        "{title} — a premium heavyweight streetwear sweatshirt with an oversized silhouette and everyday versatility. "
        "{gsm_line}"
        "Clean construction with ribbed cuffs and hem. Drop-shoulder design for a relaxed fit. "
        "{fit_line}"
        "Pre-shrunk and side-seamed for shape retention. Built to last through repeated wash cycles. "
        "{color_line}"
        "Machine wash cold. Free shipping. "
        "A wardrobe essential for streetwear fans and everyday casual wear."
    ),
    "sweatpants": (
        "{title} — premium heavyweight streetwear sweatpants designed for comfort and style. "
        "{gsm_line}"
        "Elastic waistband with drawstring. Tapered or relaxed leg depending on cut. "
        "Ribbed cuffs at the ankle for a clean, structured finish. "
        "{fit_line}"
        "Cotton-blend construction — soft, breathable, and built for all-day wear. "
        "{color_line}"
        "Machine wash cold. Free shipping. "
        "Perfect as a matching set bottom or standalone streetwear staple."
    ),
    "jeans": (
        "{title} — streetwear-influenced denim jeans with a bold, relaxed silhouette. "
        "Baggy or wide-leg cut for authentic streetwear styling. "
        "{fit_line}"
        "Durable denim construction with reinforced stitching at stress points. "
        "Available in washed and raw finish options. "
        "{color_line}"
        "Machine wash cold, hang dry recommended. Free shipping. "
        "The go-to denim choice for streetwear fits from casual to elevated."
    ),
    "shorts": (
        "{title} — premium streetwear shorts built for comfort and style in warmer months. "
        "{gsm_line}"
        "Elastic waistband with drawstring. Mid-thigh to knee length. "
        "{fit_line}"
        "Lightweight and breathable fabric construction. "
        "{color_line}"
        "Machine wash cold. Free shipping. "
        "Ideal for summer streetwear fits, athletic wear, and casual day-to-day use."
    ),
    "polo": (
        "{title} — a premium streetwear polo shirt blending classic structure with modern fit. "
        "{gsm_line}"
        "Ribbed polo collar and two-button placket. Short sleeve cut with a clean silhouette. "
        "{fit_line}"
        "Cotton pique or woven construction — structured, breathable, and easy to style. "
        "{color_line}"
        "Machine wash cold. Free shipping. "
        "A versatile piece that works dressed up or down in any streetwear rotation."
    ),
    "tank": (
        "{title} — a premium streetwear tank top designed for layering or wearing solo. "
        "{gsm_line}"
        "Sleeveless cut with a relaxed, drop-arm silhouette. "
        "{fit_line}"
        "Soft cotton construction — lightweight and breathable for all-day comfort. "
        "{color_line}"
        "Machine wash cold. Free shipping. "
        "Perfect for warm weather wear, gym sessions, or as a layering base."
    ),
    "jacket": (
        "{title} — a premium streetwear jacket built for bold style and everyday function. "
        "{gsm_line}"
        "Full-zip or button-front closure with structured collar. "
        "{fit_line}"
        "Durable outer shell with quality stitching at all seams. "
        "{color_line}"
        "Machine wash cold or dry clean depending on material. Free shipping. "
        "A statement outerwear piece for streetwear layering in any season."
    ),
    "set": (
        "{title} — a matching streetwear hoodie and jogger set built for coordinated style. "
        "{gsm_line}"
        "Hoodie features kangaroo pocket, ribbed cuffs and hem. "
        "Joggers feature elastic waistband with drawstring and ribbed ankle cuffs. "
        "{fit_line}"
        "Heavyweight cotton fleece construction — warm, structured, and durable. "
        "{color_line}"
        "Machine wash cold. Free shipping. "
        "The ultimate matching set for a clean, effortless streetwear look."
    ),
    "hat": (
        "{title} — a premium streetwear trucker hat with a structured front panel and mesh back. "
        "Foam front panel holds shape. Adjustable snap closure fits most head sizes (56-60cm). "
        "Embroidered or printed graphic on front. "
        "{color_line}"
        "Spot clean recommended. Free shipping. "
        "A clean streetwear accessory that completes any fit."
    ),
}

def strip_html(raw_html):
    if not raw_html:
        return ""
    text = re.sub(r'<table[\s\S]*?</table>', '', raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def build_optimised_description(body_html, material=None, fit=None, color=None,
                                product_title="", tags_list=None):
    if tags_list is None:
        tags_list = []
    cat      = categorize(product_title, tags_list) if product_title else "tshirt"
    gsm      = get_gsm(tags_list) if tags_list else ""
    gsm_line   = f"Made with {gsm} premium cotton fabric for a dense, durable feel. " if gsm else ""
    fit_line   = f"{fit} silhouette. " if fit else "Oversized silhouette. "
    color_line = f"Available in {color}. " if color else ""
    clean_title = re.sub(
        r'\s*[|·—\-]+\s*(Premium Streetwear|Legendary Branding[^\s]*).*$',
        '', product_title, flags=re.IGNORECASE
    ).strip() or product_title
    template    = DESC_TEMPLATES.get(cat, DESC_TEMPLATES["tshirt"])
    description = template.format(
        title=clean_title, gsm_line=gsm_line, fit_line=fit_line,
        color_line=color_line, features="",
    )
    description = re.sub(r'\s+', ' ', description).strip()
    return html.unescape(description)[:5000]


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

def build_optimised_title(product_title, tags_list, prefix=None):
    cat    = categorize(product_title, tags_list)
    fit    = get_fit(tags_list)
    gsm    = get_gsm(tags_list)
    pfx    = prefix or PREFIX_MAP.get(cat, "Premium Streetwear Apparel")
    if gsm and gsm not in pfx:
        pfx = f"{pfx} {gsm}"
    opt = f"{pfx} | {product_title} — {fit}"
    return opt[:150] if len(opt) <= 150 else opt[:147].rstrip() + "..."


# ── Apparel attribute helpers ─────────────────────────────────────────────────

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
    tg = " ".join(tags_list)
    for gsm_key, material in GSM_MATERIAL_MAP.items():
        if gsm_key in tg:
            return material
    tg_lower = tg.lower()
    if "denim" in tg_lower:        return "100% Cotton Denim"
    if "premium fleece" in tg_lower: return "80% Cotton 20% Polyester Premium Fleece"
    if "100% cotton" in tg_lower:  return "100% Cotton"
    return "Cotton Blend"

def get_gender(tags_list, option3=None):
    if option3:
        o3 = option3.lower()
        if "women" in o3 or "female" in o3: return "female"
        if "men" in o3 and "women" not in o3: return "male"
    tg = " ".join(tags_list).lower()
    if "women" in tg and "mens" not in tg: return "female"
    if "men's streetwear" in tg:           return "male"
    return "unisex"

# ── FIX 3: Expanded color normalization ───────────────────────────────────────
def normalize_color(raw_color):
    if not raw_color:
        return None
    size_values = {"XS","S","M","L","XL","2XL","3XL","4XL","5XL","XXL","XXXL"}
    if raw_color.strip().upper() in size_values:
        return None
    COLOR_NORMALIZE = {
        # Grays
        "charcoal gray": "Gray",      "charcoal grey": "Gray",   "charcoal": "Gray",
        "dark gray": "Gray",          "dark grey": "Gray",       "heather gray": "Gray",
        "graphite": "Gray",           "carbon gray": "Gray",     "dust": "Gray",
        "athletic heather": "Gray",   "dark rock ash": "Gray",   "slate gray": "Gray",
        "smoky blue": "Blue",
        # Greens
        "dark green": "Green",        "military green": "Green", "olive green": "Olive",
        "grass green": "Green",       "medium jungle green": "Green",
        "grayish green": "Green",     "dark army green": "Green","safety green": "Green",
        "blackish green": "Green",    "jungle green": "Green",
        # Blues
        "navy blue": "Navy",          "collegiate navy": "Navy", "midnight": "Navy",
        "royal blue": "Blue",         "collegiate royal": "Blue","haze blue": "Blue",
        "dusty blue": "Blue",         "hyacinth blue": "Blue",   "cow blue": "Blue",
        "grayish blue": "Blue",       "sky blue": "Blue",        "denim blue": "Blue",
        "pastell blue": "Blue",       "pastel blue": "Blue",     "light blue": "Light Blue",
        "dark blue": "Blue",
        # Pinks / Reds
        "rose pink": "Pink",          "dark pink": "Pink",       "watermelon pink": "Pink",
        "pink candy": "Pink",         "rose red": "Red",         "garnet red": "Red",
        "garnet": "Red",              "scarlet": "Red",          "burgundy": "Burgundy",
        "maroon": "Maroon",           "raspberry purple": "Purple","rose": "Pink",
        # Whites / Creams
        "off-white": "White",         "ivory": "White",          "ecru": "Cream",
        "ercu": "Cream",              "cream": "Cream",
        # Neutrals
        "sand apricot": "Beige",      "apricot": "Beige",        "taupe": "Beige",
        "khaki": "Khaki",             "americano": "Brown",      "coffee": "Brown",
        "dark yellow": "Yellow",
    }
    lower = raw_color.lower().strip()
    return COLOR_NORMALIZE.get(lower, raw_color.title())

def normalize_size(raw_size):
    if not raw_size:
        return None
    known_colors = {
        "black","white","red","blue","green","yellow","pink","purple",
        "grey","gray","navy","brown","orange","beige","cream","ivory",
        "olive","maroon","teal","coral","salmon","tan",
    }
    if raw_size.lower() in known_colors:
        return None
    cleaned = re.sub(r'\s*\(\d+\)', '', raw_size).strip()
    SIZE_NORMALIZE = {
        "xxl": "XXL", "xxxl": "3XL",
        "xs": "XS",   "s": "S",     "m": "M",   "l": "L",
        "xl": "XL",   "2xl": "2XL", "3xl": "3XL",
        "4xl": "4XL", "5xl": "5XL",
    }
    return SIZE_NORMALIZE.get(cleaned.lower(), cleaned)

def get_google_category_id(product_type):
    CATEGORY_MAP = {
        "Apparel & Accessories > Clothing > Shirts & Tops":              "212",
        "Apparel & Accessories > Clothing > Activewear > Hoodies":       "5322",
        "Apparel & Accessories > Clothing > Pants":                      "207",
        "Apparel & Accessories > Clothing > Shorts":                     "214",
        "Apparel & Accessories > Clothing > Outerwear":                  "5441",
        "Apparel & Accessories > Clothing > Outfit Sets":                "1604",
        "Apparel & Accessories > Clothing Accessories > Hats":           "178",
    }
    return CATEGORY_MAP.get(product_type, "1604")


# ── FIX 1 + 6: TARGET_MARKETS — all 56 ad-targeted countries ─────────────────
TARGET_MARKETS = [
    # ── English-speaking core ─────────────────────────────────────────────────
    {"country": "US", "lang": "en", "currency": "USD", "size_system": "US"},
    {"country": "CA", "lang": "en", "currency": "USD", "size_system": "US"},
    {"country": "GB", "lang": "en", "currency": "USD", "size_system": "UK"},
    {"country": "AU", "lang": "en", "currency": "USD", "size_system": "AU"},
    {"country": "IE", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "NZ", "lang": "en", "currency": "USD", "size_system": "AU"},
    {"country": "SG", "lang": "en", "currency": "USD", "size_system": "US"},
    # ── Western Europe ────────────────────────────────────────────────────────
    {"country": "DE", "lang": "de", "currency": "USD", "size_system": "EU"},
    {"country": "FR", "lang": "fr", "currency": "USD", "size_system": "EU"},
    {"country": "NL", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "IT", "lang": "it", "currency": "USD", "size_system": "EU"},
    {"country": "ES", "lang": "es", "currency": "USD", "size_system": "EU"},
    {"country": "SE", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "NO", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "DK", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "FI", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "BE", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "AT", "lang": "de", "currency": "USD", "size_system": "EU"},
    {"country": "CH", "lang": "de", "currency": "USD", "size_system": "EU"},
    {"country": "PT", "lang": "pt", "currency": "USD", "size_system": "EU"},  # FIX 6
    {"country": "GR", "lang": "en", "currency": "USD", "size_system": "EU"},
    # ── Eastern Europe ────────────────────────────────────────────────────────
    {"country": "PL", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "CZ", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "RO", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "HU", "lang": "en", "currency": "USD", "size_system": "EU"},
    {"country": "SK", "lang": "en", "currency": "USD", "size_system": "EU"},
    # ── Asia-Pacific ──────────────────────────────────────────────────────────
    {"country": "JP", "lang": "ja", "currency": "USD", "size_system": "JP"},
    {"country": "KR", "lang": "en", "currency": "USD", "size_system": "US"},
    {"country": "HK", "lang": "en", "currency": "USD", "size_system": "UK"},  # FIX 5
    {"country": "MY", "lang": "en", "currency": "USD", "size_system": "US"},
    {"country": "TW", "lang": "en", "currency": "USD", "size_system": "US"},
    # ── Middle East ───────────────────────────────────────────────────────────
    {"country": "AE", "lang": "en", "currency": "USD", "size_system": "US"},
    {"country": "SA", "lang": "en", "currency": "USD", "size_system": "US"},
    {"country": "IL", "lang": "en", "currency": "USD", "size_system": "US"},
    {"country": "QA", "lang": "en", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "KW", "lang": "en", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "BH", "lang": "en", "currency": "USD", "size_system": "US"},  # FIX 1
    # ── Latin America ─────────────────────────────────────────────────────────
    {"country": "MX", "lang": "es", "currency": "USD", "size_system": "US"},
    {"country": "AR", "lang": "es", "currency": "USD", "size_system": "US"},
    {"country": "CL", "lang": "es", "currency": "USD", "size_system": "US"},
    {"country": "CO", "lang": "es", "currency": "USD", "size_system": "US"},
    {"country": "EC", "lang": "es", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "PE", "lang": "es", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "DO", "lang": "es", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "SV", "lang": "es", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "GT", "lang": "es", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "JM", "lang": "en", "currency": "USD", "size_system": "UK"},  # FIX 1
    {"country": "PA", "lang": "es", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "PR", "lang": "es", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "TT", "lang": "en", "currency": "USD", "size_system": "UK"},  # FIX 1
    # ── Central Asia / Caucasus ───────────────────────────────────────────────
    {"country": "KZ", "lang": "en", "currency": "USD", "size_system": "EU"},  # FIX 1
    {"country": "AM", "lang": "en", "currency": "USD", "size_system": "EU"},  # FIX 1
    {"country": "GE", "lang": "en", "currency": "USD", "size_system": "EU"},  # FIX 1
    # ── North Africa / Levant ─────────────────────────────────────────────────
    {"country": "MA", "lang": "fr", "currency": "USD", "size_system": "EU"},  # FIX 1
    {"country": "EG", "lang": "en", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "JO", "lang": "en", "currency": "USD", "size_system": "US"},  # FIX 1
    {"country": "LB", "lang": "en", "currency": "USD", "size_system": "US"},  # FIX 1
    # ── Africa ───────────────────────────────────────────────────────────────
    {"country": "ZA", "lang": "en", "currency": "USD", "size_system": "UK"},  # FIX 1 — ZA uses UK sizing
    {"country": "NG", "lang": "en", "currency": "USD", "size_system": "UK"},  # Nigeria
    {"country": "KE", "lang": "en", "currency": "USD", "size_system": "UK"},  # Kenya
    # ── South Asia ───────────────────────────────────────────────────────────
    {"country": "IN", "lang": "en", "currency": "USD", "size_system": "US"},  # India
    # ── Southeast Asia ───────────────────────────────────────────────────────
    {"country": "VN", "lang": "en", "currency": "USD", "size_system": "US"},  # Vietnam
    # ── South America ────────────────────────────────────────────────────────
    {"country": "BR", "lang": "pt", "currency": "USD", "size_system": "US"},  # Brazil
]

def build_shipping(country: str) -> list:
    if country == "US":
        return [{
            "country": "US",
            "service": "Free Shipping (7-10 Days)",
            "price": {"value": "0.00", "currency": "USD"},
            "minHandlingTime": 0, "maxHandlingTime": 3,
            "minTransitTime": 3,  "maxTransitTime": 10,
        }]
    return [{
        "country": country,
        "service": "Free International Shipping (7-10 Days)",
        "price": {"value": "0.00", "currency": "USD"},
        "minHandlingTime": 0, "maxHandlingTime": 3,
        "minTransitTime": 7,  "maxTransitTime": 21,
    }]


# ── FIX 7: Change detection — load last-seen updated_at from GCS ─────────────
CHANGE_STATE_OBJECT = "feed_change_state.json"
GCS_BUCKET          = "lb-feed-state"

def load_change_state(sa_key_json: str) -> dict:
    """Load dict of {shopify_product_id: updated_at} from GCS."""
    from google.auth.transport.requests import Request as GoogleRequest
    import requests as rq
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_key_json),
        scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
    )
    creds.refresh(GoogleRequest())
    headers = {"Authorization": f"Bearer {creds.token}"}
    url = f"https://storage.googleapis.com/download/storage/v1/b/{GCS_BUCKET}/o/{CHANGE_STATE_OBJECT}?alt=media"
    r = rq.get(url, headers=headers, timeout=15)
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json()

def save_change_state(state: dict, sa_key_json: str) -> None:
    from google.auth.transport.requests import Request as GoogleRequest
    import requests as rq
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_key_json),
        scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
    )
    creds.refresh(GoogleRequest())
    headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
    url = f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o?uploadType=media&name={CHANGE_STATE_OBJECT}"
    rq.post(url, headers=headers, data=json.dumps(state), timeout=15).raise_for_status()
    print(f"  [change-detection] State saved — {len(state)} products tracked")


# ── Step 1: Pull all active Shopify products ──────────────────────────────────
print("\n" + "=" * 70)
print("STEP 1: Fetching active Shopify products")
print("=" * 70)

all_products = []
url    = f"https://{SHOP}/admin/api/{API_VERSION}/products.json"
params = {
    "limit":  250,
    "status": "active",
    "fields": "id,title,handle,product_type,tags,body_html,variants,images,updated_at",
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

# ── FIX 7: Load change state and filter to changed products ───────────────────
print("\n  Loading change detection state...")
try:
    change_state = load_change_state(SA_KEY_JSON)
    print(f"  Previously tracked: {len(change_state)} products")
except Exception as e:
    print(f"  WARNING: Could not load change state ({e}) — processing all products")
    change_state = {}

changed_products = []
unchanged_count  = 0
for p in all_products:
    pid        = str(p["id"])
    updated_at = p.get("updated_at", "")
    if change_state.get(pid) != updated_at:
        changed_products.append(p)
    else:
        unchanged_count += 1

print(f"  Changed / new products: {len(changed_products)}")
print(f"  Unchanged (skipping):   {unchanged_count}")

# If first run or forced full sync (>50% changed), process everything
if unchanged_count == 0 or len(changed_products) / len(all_products) > 0.5:
    print("  Full sync mode — processing all products")
    changed_products = all_products


# ── Step 2: Load rotation state ───────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 2: Loading rotation state + GMC performance data")
print("=" * 70)

TODAY = date.today().isoformat()

# FIX 8: Fallback on rotation module failure — feed never fails silently
ROTATION_AVAILABLE = True
try:
    rotation_state = load_state(SA_KEY_JSON)
    perf_data      = fetch_free_listing_performance(SA_KEY_JSON)
    print(f"  Today          : {TODAY}")
    print(f"  Products in state: {len(rotation_state.get('products', {}))}")
    print(f"  Offer IDs with perf data: {len(perf_data)}")
except Exception as e:
    print(f"  WARNING: Rotation module failed ({e}) — using static PREFIX_MAP fallback")
    ROTATION_AVAILABLE = False
    rotation_state = {"last_run": TODAY, "products": {}}
    perf_data      = {}


# ── Step 3: Build enriched records ────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3: Building enriched variant records")
print("=" * 70)

records = []

for product in changed_products:
    pid          = str(product["id"])
    title        = product["title"]
    handle       = product["handle"]
    tags_raw     = product.get("tags", "") or ""
    tags_list    = [t.strip() for t in tags_raw.split(",") if t.strip()]
    images       = product.get("images", [])
    primary_image = images[0]["src"] if images else ""
    product_type  = product.get("product_type", "") or ""

    cat        = categorize(title, tags_list)
    gsm        = get_gsm(tags_list)
    fit        = get_fit(tags_list)
    material   = get_material(tags_list)
    google_cat = get_google_category_id(product_type)
    body_html  = product.get("body_html", "") or ""
    age_group  = get_age_group(tags_list)  # FIX 9

    # FIX 2: itemGroupId — groups all variants under one parent listing
    item_group_id = f"lb_{pid}"

    # FIX 8: Rotation with fallback
    if ROTATION_AVAILABLE:
        try:
            rot_prefix, rot_reason = get_rotated_prefix(
                handle, cat, product.get("variants", []), perf_data,
                rotation_state, TODAY, gsm=gsm
            )
        except Exception as e:
            print(f"  WARNING: Rotation failed for {handle} ({e}) — using static prefix")
            rot_prefix = f"{PREFIX_MAP.get(cat, 'Premium Streetwear Apparel')}{' ' + gsm if gsm else ''}"
            rot_reason = "FALLBACK"
    else:
        rot_prefix = f"{PREFIX_MAP.get(cat, 'Premium Streetwear Apparel')}{' ' + gsm if gsm else ''}"
        rot_reason = "STATIC_FALLBACK"

    for variant in product.get("variants", []):
        vid       = variant["id"]
        price     = variant.get("price", "0.00")
        inventory = variant.get("inventory_quantity", 1) or 0
        avail     = "in stock" if inventory > 0 else "out of stock"

        raw_opt1 = variant.get("option1") or ""
        raw_opt2 = variant.get("option2") or ""
        raw_opt3 = variant.get("option3") or ""

        color     = normalize_color(raw_opt1)
        size      = normalize_size(raw_opt2)
        if not color and raw_opt1:
            maybe_size = normalize_size(raw_opt1)
            if maybe_size:
                size  = maybe_size
                color = None

        gender    = get_gender(tags_list, raw_opt3 or None)
        size_type = get_size_type(tags_list, title)  # FIX 4

        var_title = variant.get("title", "") or ""
        if var_title.upper() not in ("DEFAULT TITLE", "DEFAULT", ""):
            display_title = f"{build_optimised_title(title, tags_list, rot_prefix)} - {var_title}"
        else:
            display_title = build_optimised_title(title, tags_list, rot_prefix)
        display_title = display_title[:150]

        var_img_id = variant.get("image_id")
        var_image  = primary_image
        if var_img_id:
            for img in images:
                if img["id"] == var_img_id:
                    var_image = img["src"]
                    break

        description = build_optimised_description(
            body_html, material=material, fit=fit,
            color=color, product_title=title, tags_list=tags_list,
        )

        for market in TARGET_MARKETS:
            mcc  = market["country"]
            lang = market["lang"]
            cur  = market["currency"]
            ss   = market["size_system"]

            record = {
                "id":                    f"online:{lang}:{mcc}:{vid}",
                "offerId":               str(vid),
                "title":                 display_title,
                "description":           description,
                "link":                  f"{STORE_URL}/products/{handle}",
                "imageLink":             var_image,
                "availability":          avail,
                "price":                 {"value": price, "currency": cur},
                "condition":             "new",
                "channel":               "online",
                "contentLanguage":       lang,
                "targetCountry":         mcc,
                "brand":                 "Legendary Branding",
                "identifierExists":      False,
                "googleProductCategory": google_cat,
                "gender":                gender,
                "ageGroup":              age_group,   # FIX 9
                "sizeSystem":            ss,
                "sizeType":              size_type,   # FIX 4
                "itemGroupId":           item_group_id,  # FIX 2
                "shipping":              build_shipping(mcc),
            }

            if color:    record["color"]    = color
            if size:     record["sizes"]    = [size]
            if material: record["material"] = material

            records.append(record)

# FIX 8: Save rotation state with fallback
if ROTATION_AVAILABLE:
    print("\n  Saving rotation state...")
    rotation_state["last_run"] = TODAY
    try:
        save_state(rotation_state, SA_KEY_JSON)
    except Exception as e:
        print(f"  WARNING: Could not save rotation state: {e} — continuing")

print(f"\n  Variant records built: {len(records)}")

# Coverage report
has_color    = sum(1 for r in records if r.get("color"))
has_size     = sum(1 for r in records if r.get("sizes"))
has_material = sum(1 for r in records if r.get("material"))
markets_covered = len(TARGET_MARKETS)
print(f"  MARKETS: {markets_covered}")
print(f"  color    : {has_color}/{len(records)} ({has_color*100//max(len(records),1)}%)")
print(f"  size     : {has_size}/{len(records)} ({has_size*100//max(len(records),1)}%)")
print(f"  material : {has_material}/{len(records)} ({has_material*100//max(len(records),1)}%)")
print(f"  gender   : {len(records)}/{len(records)} (100%)")
print(f"  ageGroup : {len(records)}/{len(records)} (100%)")
print(f"  itemGroupId: {len(records)}/{len(records)} (100%)")


# ── Step 4: Batch upsert into GMC ────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 4: Upserting into Google Merchant Center")
print("=" * 70)

BATCH_SIZE = 1000
inserted   = 0
errors     = 0
error_sample = []

for i in range(0, len(records), BATCH_SIZE):
    batch   = records[i:i + BATCH_SIZE]
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
    for attempt in range(1, 4):
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
            break
        except HttpError as e:
            print(f"  Batch {batch_num} HTTP error (attempt {attempt}/3): {e}")
            if attempt == 3: errors += len(batch)
            else: time.sleep(2 ** attempt)
        except Exception as e:
            print(f"  Batch {batch_num} error (attempt {attempt}/3): {e}")
            if attempt == 3: errors += len(batch)
            else: time.sleep(2 ** attempt)
    time.sleep(1)


# ── FIX 7: Update change detection state ─────────────────────────────────────
if inserted > 0:
    print("\n  Updating change detection state...")
    try:
        for p in changed_products:
            change_state[str(p["id"])] = p.get("updated_at", "")
        save_change_state(change_state, SA_KEY_JSON)
    except Exception as e:
        print(f"  WARNING: Could not save change state: {e}")


# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUPPLEMENTAL FEED v2 COMPLETE")
print("=" * 70)
print(f"  Products processed  : {len(changed_products)} (of {len(all_products)} active)")
print(f"  Variants upserted   : {inserted}")
print(f"  Errors              : {errors}")
print(f"  Markets             : {markets_covered}")
if error_sample:
    print("\n  SAMPLE ERRORS:")
    for es in error_sample:
        print(f"    [{es['batchId']}] {es['errors']}")
