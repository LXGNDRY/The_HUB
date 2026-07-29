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
