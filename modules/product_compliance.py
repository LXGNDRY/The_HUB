"""
product_compliance.py

Shared logic for determining country of origin (COO) and harmonized system
(HS) codes for Legendary Branding products.

Used by:
  - api/routers/webhooks.py  (automatic on products/create)
  - scripts/fix_shopify_country_hs.py  (batch correction runs)

COO resolution order:
  1. Product tag matching `coo:XX`  (e.g. `coo:US` for rare US-origin items)
  2. DEFAULT_COO env var (default: CN — most products ship direct from China)

HS codes are resolved from the product's taxonomy type string, with a
keyword-based title fallback. All codes are 6-digit, no separator.
"""

import os
import logging

logger = logging.getLogger("gcp-bot.product_compliance")

DEFAULT_COO: str = os.getenv("DEFAULT_COO", "CN")

# ── Google Shopping taxonomy map ─────────────────────────────────────────────
# Maps informal/legacy Shopify product_type values → canonical full taxonomy string.
# Keys are lower-cased at match time so casing doesn't matter.
TAXONOMY_MAP: dict[str, str] = {
    "t shirt":    "Apparel & Accessories > Clothing > Shirts & Tops",
    "t-shirt":    "Apparel & Accessories > Clothing > Shirts & Tops",
    "tshirt":     "Apparel & Accessories > Clothing > Shirts & Tops",
    "tee":        "Apparel & Accessories > Clothing > Shirts & Tops",
    "tank top":   "Apparel & Accessories > Clothing > Shirts & Tops",
    "tank":       "Apparel & Accessories > Clothing > Shirts & Tops",
    "polo":       "Apparel & Accessories > Clothing > Polo",
    "hoodie":     "Apparel & Accessories > Clothing > Activewear > Hoodies",
    "sweatshirt": "Apparel & Accessories > Clothing > Activewear > Hoodies",
    "crewneck":   "Apparel & Accessories > Clothing > Activewear > Hoodies",
    "fleece":     "Apparel & Accessories > Clothing > Activewear > Hoodies",
    "jeans":      "Apparel & Accessories > Clothing > Pants",
    "sweatpants": "Apparel & Accessories > Clothing > Pants",
    "joggers":    "Apparel & Accessories > Clothing > Pants",
    "pants":      "Apparel & Accessories > Clothing > Pants",
    "leggings":   "Apparel & Accessories > Clothing > Pants",
    "shorts":     "Apparel & Accessories > Clothing > Shorts",
    "hat":        "Apparel & Accessories > Clothing Accessories > Hats",
    "cap":        "Apparel & Accessories > Clothing Accessories > Hats",
    "beanie":     "Apparel & Accessories > Clothing Accessories > Hats",
    "jacket":     "Apparel & Accessories > Clothing > Outerwear",
    "windbreaker": "Apparel & Accessories > Clothing > Outerwear",
    "bomber":     "Apparel & Accessories > Clothing > Outerwear",
    "vest":       "Apparel & Accessories > Clothing > Outerwear",
    "outfit set": "Apparel & Accessories > Clothing > Outfit Sets",
    "tracksuit":  "Apparel & Accessories > Clothing > Outfit Sets",
    "lounge set": "Apparel & Accessories > Clothing > Outfit Sets",
    "matching set": "Apparel & Accessories > Clothing > Outfit Sets",
    "sunglasses": "Apparel & Accessories > Clothing Accessories > Sunglasses",
    "backpack":   "Apparel & Accessories > Handbags, Wallets & Cases",
    "bag":        "Apparel & Accessories > Handbags, Wallets & Cases",
    "watch box":  "Apparel & Accessories > Jewelry > Watch Accessories > Watch Boxes",
}

# Set of canonical full taxonomy strings for fast membership checks
_CANONICAL_TYPES: frozenset = frozenset(TAXONOMY_MAP.values())


def resolve_product_type(product_type: str, title: str = "") -> str:
    """
    Normalize a product_type value to a canonical Google Shopping taxonomy string.

    Resolution order:
      1. Already a known full taxonomy string → return as-is
      2. Exact case-insensitive match in TAXONOMY_MAP → map it
      3. Keyword scan of (product_type + title) against TAXONOMY_MAP keys
      4. Default → Shirts & Tops (broadest branded-apparel bucket)
    """
    pt = product_type.strip()
    if pt in _CANONICAL_TYPES:
        return pt

    pt_lower = pt.lower()
    # Exact map lookup (case-insensitive)
    if pt_lower in TAXONOMY_MAP:
        return TAXONOMY_MAP[pt_lower]

    # Keyword scan of combined type + title text
    combined = (pt + " " + title).lower()
    for keyword, taxonomy in TAXONOMY_MAP.items():
        if keyword in combined:
            return taxonomy

    return "Apparel & Accessories > Clothing > Shirts & Tops"


# ── HS code map keyed on product-type taxonomy strings ───────────────────────
# Primary cotton composition assumed — most common for branded apparel.
HS_CODE_MAP: dict[str, str] = {
    "Apparel & Accessories > Clothing > Shirts & Tops":          "610910",  # cotton knit T-shirts/vests
    "Apparel & Accessories > Clothing > Activewear > Hoodies":   "611020",  # cotton jerseys/sweatshirts
    "Apparel & Accessories > Clothing > Pants":                  "610342",  # cotton knit trousers/tracksuit bottoms
    "Apparel & Accessories > Clothing > Shorts":                 "610342",  # cotton knit shorts
    "Apparel & Accessories > Clothing Accessories > Hats":       "650500",  # hats and headgear
    "Apparel & Accessories > Clothing Accessories > Sunglasses": "900410",  # sunglasses
    "Apparel & Accessories > Clothing > Outerwear":              "610120",  # cotton knit jackets
    "Apparel & Accessories > Clothing > Outfit Sets":            "621133",  # track suits / lounge sets
    "Apparel & Accessories > Clothing > Polo":                   "610510",  # cotton knit polo shirts
}


def infer_hs_code(product_type: str, title: str) -> str:
    """
    Return an HS code for a product.

    Tries an exact match on the taxonomy product_type string first,
    then falls back to keyword scanning of type + title.
    Default: 610910 (cotton knit T-shirts — broadest branded-apparel bucket).
    """
    exact = HS_CODE_MAP.get(product_type.strip())
    if exact:
        return exact

    t = (product_type + " " + title).lower()
    if any(k in t for k in ["hoodie", "sweatshirt", "hooded", "fleece", "crewneck"]):
        return "611020"
    if any(k in t for k in ["pant", "jogger", "trackpant", "sweatpant", "jean", "denim"]):
        return "610342"
    if "short" in t:
        return "610342"
    if any(k in t for k in ["hat", "cap", "beanie", "snapback", "trucker"]):
        return "650500"
    if any(k in t for k in ["sunglass", "shade"]):
        return "900410"
    if any(k in t for k in ["jacket", "windbreaker", "bomber", "outerwear"]):
        return "610120"
    if any(k in t for k in ["set", "tracksuit", "outfit", "lounge"]):
        return "621133"
    if "polo" in t:
        return "610510"
    return "610910"


# ── GMC numeric category ID map ──────────────────────────────────────────────
# Maps canonical taxonomy strings → official Google taxonomy numeric IDs.
# Written to the google_product_category metafield so GMC uses the right
# category for disapproval rules, required-attribute checks, and feed matching.
GMC_CATEGORY_ID_MAP: dict[str, str] = {
    "Apparel & Accessories > Clothing > Shirts & Tops":                       "212",
    "Apparel & Accessories > Clothing > Activewear > Hoodies":                "5322",
    "Apparel & Accessories > Clothing > Pants":                               "207",
    "Apparel & Accessories > Clothing > Shorts":                              "2271",
    "Apparel & Accessories > Clothing > Polo":                                "3471",
    "Apparel & Accessories > Clothing > Outerwear":                           "1831",
    "Apparel & Accessories > Clothing > Outfit Sets":                         "1604",
    "Apparel & Accessories > Clothing Accessories > Hats":                    "178",
    "Apparel & Accessories > Clothing Accessories > Sunglasses":              "176",
    "Apparel & Accessories > Handbags, Wallets & Cases":                      "6",
    "Apparel & Accessories > Jewelry > Watch Accessories > Watch Boxes":      "191",
}

_DEFAULT_GMC_CATEGORY_ID = "212"  # Shirts & Tops — broadest branded-apparel bucket


def resolve_gmc_category_id(canonical_type: str) -> str:
    """Return the numeric Google taxonomy ID for a canonical taxonomy string."""
    return GMC_CATEGORY_ID_MAP.get(canonical_type.strip(), _DEFAULT_GMC_CATEGORY_ID)


# ── Product weight map (grams) ───────────────────────────────────────────────
# Default shipping weights per canonical taxonomy string.
# Values are conservative mid-range estimates for branded apparel (no packaging).
# Used to fill missing variant weights so shipping rates calculate correctly.
WEIGHT_MAP_G: dict[str, float] = {
    "Apparel & Accessories > Clothing > Shirts & Tops":                       200.0,   # tee / tank
    "Apparel & Accessories > Clothing > Activewear > Hoodies":                550.0,   # hoodie / sweatshirt
    "Apparel & Accessories > Clothing > Pants":                               450.0,   # sweatpants / joggers
    "Apparel & Accessories > Clothing > Shorts":                              280.0,   # shorts
    "Apparel & Accessories > Clothing > Polo":                                220.0,   # polo shirt
    "Apparel & Accessories > Clothing > Outerwear":                           700.0,   # jacket / windbreaker
    "Apparel & Accessories > Clothing > Outfit Sets":                         750.0,   # tracksuit / lounge set
    "Apparel & Accessories > Clothing Accessories > Hats":                    100.0,   # cap / beanie
    "Apparel & Accessories > Clothing Accessories > Sunglasses":               30.0,   # sunglasses
    "Apparel & Accessories > Handbags, Wallets & Cases":                      400.0,   # bag / backpack
    "Apparel & Accessories > Jewelry > Watch Accessories > Watch Boxes":      300.0,   # watch box
}

_DEFAULT_WEIGHT_G = 200.0  # Shirts & Tops — safest fallback for unclassified apparel


def resolve_product_weight_g(canonical_type: str) -> float:
    """Return the default weight in grams for a canonical taxonomy string."""
    return WEIGHT_MAP_G.get(canonical_type.strip(), _DEFAULT_WEIGHT_G)


def resolve_coo(tags: list) -> str:
    """
    Return the country of origin code for a product.

    Checks for a `coo:XX` tag first (e.g. `coo:US` for US-origin items).
    Falls back to DEFAULT_COO env var (default: CN).
    """
    for tag in tags:
        tag = tag.strip()
        if tag.lower().startswith("coo:"):
            code = tag.split(":", 1)[1].upper()
            logger.debug("COO resolved from tag '%s' → %s", tag, code)
            return code
    return DEFAULT_COO
