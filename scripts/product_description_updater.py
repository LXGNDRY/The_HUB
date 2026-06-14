#!/usr/bin/env python3
"""
Legendary Branding — Mass Product Description Engine
=====================================================
Fetches ALL products from Shopify via GraphQL cursor-based pagination,
generates brand-consistent HTML descriptions using a smart template engine,
and pushes updates via productUpdate mutation.

Usage:
    python product_description_updater.py           # DRY RUN (preview only)
    python product_description_updater.py --execute  # LIVE push to Shopify

Env vars required:
    SHOPIFY_ADMIN_TOKEN   — Shopify Admin API token

Outputs:
    /home/user/workspace/logs/description_updates.log
    /home/user/workspace/backups/original_descriptions.json
"""

import os
import sys
import json
import time
import logging
import re
import argparse
from datetime import datetime

import requests

# ─── Configuration ────────────────────────────────────────────────────────────

SHOP_URL     = "lngndny.myshopify.com"
API_VERSION  = "2024-01"
GRAPHQL_URL  = f"https://{SHOP_URL}/admin/api/{API_VERSION}/graphql.json"
# Use relative paths so the script works both locally and in GitHub Actions
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH     = os.path.join(_BASE, "logs", "description_updates.log")
BACKUP_PATH  = os.path.join(_BASE, "backups", "original_descriptions.json")

os.makedirs(os.path.dirname(LOG_PATH),   exist_ok=True)
os.makedirs(os.path.dirname(BACKUP_PATH), exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ─── Shopify GraphQL helpers ───────────────────────────────────────────────────

def get_headers():
    token = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
    if not token:
        raise EnvironmentError("SHOPIFY_ADMIN_TOKEN is not set in the environment.")
    return {
        "Content-Type":                "application/json",
        "X-Shopify-Access-Token":      token,
    }


def gql_request(query: str, variables: dict = None, retries: int = 5) -> dict:
    """Execute a GraphQL request with exponential backoff on 429."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    for attempt in range(retries):
        try:
            resp = requests.post(GRAPHQL_URL, json=payload, headers=get_headers(), timeout=30)
        except requests.RequestException as e:
            log.warning(f"Network error (attempt {attempt+1}): {e}")
            time.sleep(2 ** attempt)
            continue

        if resp.status_code == 429:
            wait = 2 ** (attempt + 1)
            log.warning(f"Rate limited (429). Waiting {wait}s...")
            time.sleep(wait)
            continue

        if resp.status_code != 200:
            log.error(f"HTTP {resp.status_code}: {resp.text[:300]}")
            raise RuntimeError(f"HTTP {resp.status_code} from Shopify")

        data = resp.json()
        if "errors" in data:
            log.error(f"GraphQL errors: {data['errors']}")
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        return data

    raise RuntimeError("Exceeded max retries for Shopify request.")


# ─── Fetch all products ────────────────────────────────────────────────────────

PRODUCTS_QUERY = """
query FetchProducts($after: String) {
  products(first: 50, after: $after) {
    edges {
      node {
        id
        title
        productType
        tags
        bodyHtml
        vendor
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


def fetch_all_products() -> list:
    products = []
    cursor   = None
    page     = 1

    while True:
        log.info(f"Fetching products page {page}...")
        variables = {"after": cursor} if cursor else {}
        data      = gql_request(PRODUCTS_QUERY, variables)
        edges     = data["data"]["products"]["edges"]
        page_info = data["data"]["products"]["pageInfo"]

        for edge in edges:
            products.append(edge["node"])

        log.info(f"  Page {page}: got {len(edges)} products (total so far: {len(products)})")

        if not page_info["hasNextPage"]:
            break

        cursor = page_info["endCursor"]
        page  += 1
        time.sleep(0.3)   # polite delay

    log.info(f"Fetched {len(products)} total products.")
    return products


# ─── Size tables ──────────────────────────────────────────────────────────────

TH = '<th style="padding: 8px 12px; border: 1px solid #333;">'
TD = '<td style="padding: 8px 12px; border: 1px solid #ddd;">'
TDB = '<td style="padding: 8px 12px; border: 1px solid #ddd; font-weight: bold;">'


def _table_wrap(header_row: str, body_rows: str, note: str = "") -> str:
    note_html = (
        f'<p style="text-align: center; font-size: 12px; color: #666; margin-top: 8px;">'
        f'{note}</p>'
    ) if note else ""
    return (
        '<div style="text-align: center; margin: 12px 0 24px 0;">\n'
        '<table style="margin: 0 auto; border-collapse: collapse; font-family: Arial, sans-serif; font-size: 13px;">\n'
        '<thead>\n'
        f'<tr style="background: #111; color: #fff;">{header_row}</tr>\n'
        '</thead>\n'
        '<tbody>\n'
        f'{body_rows}'
        '</tbody>\n'
        '</table>\n'
        f'{note_html}'
        '</div>'
    )


def _row(cells: list, bold_first: bool = True) -> str:
    parts = []
    for i, c in enumerate(cells):
        tag = TDB if (i == 0 and bold_first) else TD
        parts.append(f"{tag}{c}</td>")
    return "<tr>" + "".join(parts) + "</tr>\n"


# T-SHIRT size table: XS–5XL, 9 sizes
TSHIRT_SIZES = [
    ("XS", "41.34", "105", "25.59", "65",  "20.47", "52",  "8.26", "21"),
    ("S",  "43.30", "110", "26.80", "68",  "21.30", "54",  "8.70", "22"),
    ("M",  "45.30", "115", "28.00", "71",  "22.00", "56",  "9.10", "23"),
    ("L",  "47.20", "120", "29.10", "74",  "22.80", "58",  "9.40", "24"),
    ("XL", "49.20", "125", "30.30", "77",  "23.60", "60",  "9.80", "25"),
    ("2XL","51.20", "130", "31.50", "80",  "24.40", "62", "10.20", "26"),
    ("3XL","53.10", "135", "32.70", "83",  "25.20", "64", "10.60", "27"),
    ("4XL","55.10", "140", "33.90", "86",  "26.00", "66", "11.00", "28"),
    ("5XL","57.10", "145", "35.00", "89",  "26.80", "68", "11.40", "29"),
]

def tshirt_size_table() -> str:
    header = (
        f"{TH}SIZE</th>"
        f"{TH}CHEST (IN)</th>{TH}LENGTH (IN)</th>"
        f"{TH}SHOULDER (IN)</th>{TH}SLEEVE (IN)</th>"
        f"{TH}CHEST (CM)</th>{TH}LENGTH (CM)</th>"
        f"{TH}SHOULDER (CM)</th>{TH}SLEEVE (CM)</th>"
    )
    rows = ""
    for s in TSHIRT_SIZES:
        rows += _row([s[0], s[1], s[3], s[5], s[7], s[2], s[4], s[6], s[8]])
    return _table_wrap(header, rows, "Measurements are approximate · garment laid flat · ±1 inch tolerance.")


# Sweatshirt/Hoodie table: S–5XL
SWEAT_SIZES = [
    ("S",   "20", "51", "27", "69", "17", "43", "24", "61"),
    ("M",   "22", "56", "28", "71", "18.5","47","24.5","62"),
    ("L",   "24", "61", "29", "74", "20", "51", "25", "64"),
    ("XL",  "26", "66", "30", "76", "21.5","55","25.5","65"),
    ("2XL", "28", "71", "31", "79", "23", "58", "26", "66"),
    ("3XL", "30", "76", "32", "81", "24.5","62","26.5","67"),
    ("4XL", "32", "81", "33", "84", "26", "66", "27", "69"),
    ("5XL", "34", "86", "34", "86", "27.5","70","27.5","70"),
]

def sweat_size_table() -> str:
    header = (
        f"{TH}SIZE</th>"
        f"{TH}CHEST (IN)</th>{TH}LENGTH (IN)</th>"
        f"{TH}SHOULDER (IN)</th>{TH}SLEEVE (IN)</th>"
        f"{TH}CHEST (CM)</th>{TH}LENGTH (CM)</th>"
        f"{TH}SHOULDER (CM)</th>{TH}SLEEVE (CM)</th>"
    )
    rows = ""
    for s in SWEAT_SIZES:
        rows += _row([s[0], s[1], s[3], s[5], s[7], s[2], s[4], s[6], s[8]])
    return _table_wrap(header, rows, "Measurements are approximate · garment laid flat · ±1 inch tolerance.")


# Shorts table
SHORTS_SIZES = [
    ("XS", "29⅞", "37",  "76",  "94"),
    ("S",  "31½", "38⅝", "80",  "98"),
    ("M",  "33⅛", "40⅛", "84",  "102"),
    ("L",  "36¼", "43¼", "92",  "110"),
    ("XL", "39⅜", "46½", "100", "118"),
    ("2XL","42½", "49⅝", "108", "126"),
    ("3XL","45⅝", "52¾", "116", "134"),
]

def shorts_size_table() -> str:
    header = (
        f"{TH}SIZE</th>"
        f"{TH}WAIST (IN)</th>{TH}HIPS (IN)</th>"
        f"{TH}WAIST (CM)</th>{TH}HIPS (CM)</th>"
    )
    rows = ""
    for s in SHORTS_SIZES:
        rows += _row([s[0], s[1], s[2], s[3], s[4]])
    return _table_wrap(header, rows, "Measurements are approximate · waistband laid flat · ±1 inch tolerance.")


# Pants / Joggers table
PANTS_SIZES = [
    ("S",   "28–30", "71–76"),
    ("M",   "31–33", "79–84"),
    ("L",   "34–36", "86–91"),
    ("XL",  "37–39", "94–99"),
    ("2XL", "40–42", "102–107"),
    ("3XL", "43–45", "109–114"),
]

def pants_size_table() -> str:
    header = f"{TH}SIZE</th>{TH}WAIST (IN)</th>{TH}WAIST (CM)</th>"
    rows = ""
    for s in PANTS_SIZES:
        rows += _row([s[0], s[1], s[2]])
    return _table_wrap(header, rows, "Measurements are approximate · ±1 inch tolerance.")


# Hat / Accessory table
def hat_size_table() -> str:
    header = f"{TH}FIT</th>{TH}HEAD CIRC. (IN)</th>{TH}HEAD CIRC. (CM)</th>"
    rows = (
        _row(["One Size Adjustable", "21.5–23.5", "54.6–59.7"])
    )
    return _table_wrap(header, rows, "Adjustable snapback/strap fits most head sizes.")


# Jacket table (reuse sweat)
def jacket_size_table() -> str:
    return sweat_size_table()


# ─── Selling-story & content engine ───────────────────────────────────────────

SECTION_H2 = (
    'style="text-align: center; font-family: \'Bebas Neue\', \'Oswald\', \'Arial Narrow\', sans-serif; '
    'letter-spacing: 0.1em; text-transform: uppercase; font-weight: bold; margin-top: 28px;"'
)
TITLE_H2 = (
    'style="text-align: center; font-family: \'Bebas Neue\', \'Oswald\', \'Arial Narrow\', sans-serif; '
    'letter-spacing: 0.08em; text-transform: uppercase; font-weight: bold; font-size: 1.6em;"'
)


def extract_gsm(tags: list, title: str) -> str:
    """Pull GSM value from tags or title."""
    for tag in tags:
        m = re.search(r'(\d{2,3})\s*[Gg][Ss][Mm]', tag)
        if m:
            return m.group(0).upper().replace(" ", "")
    m = re.search(r'(\d{2,3})\s*[Gg][Ss][Mm]', title)
    if m:
        return m.group(0).upper().replace(" ", "")
    return "Heavyweight"


def tag_has(tags: list, *keywords) -> bool:
    tags_lower = [t.lower() for t in tags]
    return any(kw.lower() in t for kw in keywords for t in tags_lower)


def classify_product(product: dict) -> str:
    """
    Returns one of: tshirt | hoodie | sweatshirt | jacket | shorts | pants | hat | other
    Uses productType first, then falls back to tags + title.
    """
    ptype = (product.get("productType") or "").lower()
    title = (product.get("title") or "").lower()
    tags  = [t.lower() for t in product.get("tags", [])]
    all_text = ptype + " " + title + " " + " ".join(tags)

    if any(k in all_text for k in ["trucker hat", "foam trucker", "snapback", "> hats"]):
        return "hat"
    if any(k in all_text for k in ["> shorts", "athletic shorts", "sweat shorts", "casual shorts"]):
        return "shorts"
    if any(k in all_text for k in ["> pants", "joggers", "sweatpants", "jeans", "denim"]):
        return "pants"
    if any(k in all_text for k in ["jacket", "windbreaker", "poplin jacket", "varsity jacket", "zip-up jacket"]):
        return "jacket"
    if any(k in all_text for k in ["zip-up hoodie", "zip up hoodie", "hoodie", "pullover hoodie", "boxy fit hoodie", "graphic hoodie", "> hoodies"]):
        return "hoodie"
    if any(k in all_text for k in ["crewneck", "sweatshirt", "fleece crewneck", "1/4 zip", "quarter zip"]):
        return "sweatshirt"
    if any(k in all_text for k in ["> shirts & tops", "t-shirt", "tee", "tank top", "polo", "crop"]):
        return "tshirt"
    return "tshirt"  # safe default


def garment_label(pclass: str) -> str:
    return {
        "tshirt":     "T-Shirt",
        "hoodie":     "Hoodie",
        "sweatshirt": "Sweatshirt",
        "jacket":     "Jacket",
        "shorts":     "Shorts",
        "pants":      "Pants",
        "hat":        "Hat / Accessory",
        "other":      "Apparel",
    }.get(pclass, "Apparel")


# ── Selling stories — product-name-driven ────────────────────────────────────

def generate_selling_story(title: str, tags: list, pclass: str) -> str:
    """
    Returns a 2–3 sentence brand-specific selling story.
    Uses title keywords and tags to customise every story.
    NO shipping language whatsoever.
    """
    t = title.lower()
    tags_lower = " ".join(tags).lower()
    all_text = t + " " + tags_lower

    # ── Champion collabs
    if "champion" in all_text:
        if "jacket" in pclass or "jacket" in t:
            return (
                f"The <strong>{title}</strong> is where Legendary Branding's street sensibility "
                "meets Champion's proven outerwear heritage — a lightweight layer that goes from "
                "the block to the game without skipping a beat. "
                "Water-resistant micro poplin shell, a packable build, and the signature Champion quality "
                "make it the kind of jacket that earns a permanent spot in your rotation. "
                "This is collaborative streetwear done right — nothing forced, everything earned."
            )
        return (
            f"The <strong>{title}</strong> fuses Legendary Branding's street credibility "
            "with Champion's iconic heritage into a piece that needs no introduction. "
            "Heavyweight fleece, clean proportions, and a collab logo that lands every time "
            "make this the sweatshirt you reach for when the fit has to say something before "
            "you do. "
            "Built to be lived in and built to last."
        )

    # ── Neverdy sub-brand
    if "neverdy" in all_text:
        if "eagle" in all_text:
            return (
                f"The <strong>{title}</strong> carries the Neverdy eagle graphic — a symbol of "
                "focus, altitude, and the refusal to settle. "
                "The snow-wash finish gives it a worn-in feel straight out of the bag, "
                "like a piece that has already been somewhere worth going. "
                "Heavyweight cotton, oversized cut, and the kind of graphic that stops people mid-sentence."
            )
        if "skull" in all_text or "spine" in all_text or "ribs" in all_text:
            return (
                f"The <strong>{title}</strong> is Neverdy at its most raw — anatomical artwork "
                "printed on premium heavyweight cotton that hits different when the graphic does the talking. "
                "The oversized boxy cut gives it the space to breathe, and the 100% cotton construction "
                "means it softens with every wash without losing its edge. "
                "Wear it for the statement. Keep it for the comfort."
            )
        if "no risk no story" in all_text:
            return (
                f"The <strong>{title}</strong> carries the Neverdy ethos right on the chest — "
                "No Risk, No Story. "
                "Built from heavyweight fleece in a boxy silhouette, it is a piece for people who "
                "move with intention and dress to match. "
                "This hoodie is not decoration — it is a declaration."
            )
        return (
            f"The <strong>{title}</strong> is a Neverdy statement piece — bold graphics on "
            "a heavyweight cotton body that means business from the first wear. "
            "The oversized drop-shoulder cut sits effortlessly across the chest and "
            "keeps the silhouette clean whether you are layering up or wearing it solo. "
            "Neverdy x Legendary Branding: built for those who never settle."
        )

    # ── Marque Légendaire sub-brand
    if "marque" in all_text or "légendaire" in all_text or "legendaraire" in all_text:
        if "camo" in all_text:
            return (
                f"The <strong>{title}</strong> takes Marque Légendaire's elevated aesthetic "
                "into tactical territory with an all-over camo print cut into a boxy cropped silhouette. "
                "The heavyweight construction keeps it substantial while the fit stays modern and easy to style. "
                "Pattern-forward, brand-conscious, and built for the front row."
            )
        if "varsity" in all_text:
            return (
                f"The <strong>{title}</strong> is Marque Légendaire's take on the varsity jacket — "
                "a 360GSM premium streetwear outer layer that bridges the gap between athletic history "
                "and contemporary fashion without apology. "
                "Drop-shoulder construction, clean lines, and the Marque Légendaire identity on the chest "
                "make this the piece that ties a fit together. "
                "Wear it like you earned it."
            )
        if "motion face" in all_text:
            return (
                f"The <strong>{title}</strong> wears the Marque Légendaire Motion Face artwork — "
                "a layered graphic that captures movement, identity, and the energy of the brand "
                "in a single image. "
                "Heavyweight cropped construction keeps it compact and intentional, "
                "pairing seamlessly with wide-leg denim or cargos. "
                "Statement streetwear that moves with you."
            )
        if "laugh" in all_text:
            return (
                f"The <strong>{title}</strong> brings the Marque Légendaire Laugh It Up artwork "
                "to a heavyweight cropped tee — expressive, bold, and impossible to ignore. "
                "The waist-cropped boxy cut is made for a layered fit where the tee shows just enough "
                "to let the graphic speak. "
                "Lightweight enough for warm days, heavy enough to feel premium every time."
            )
        if "zip" in all_text and "hoodie" in all_text:
            return (
                f"The <strong>{title}</strong> brings Marque Légendaire's signature weight "
                "to a zip-up silhouette — structured, heavy, and built to be a cornerstone of the fit. "
                "The boxy cropped profile and heavyweight fleece create a layer that sits clean "
                "over everything from tees to tanks. "
                "A wardrobe anchor for anyone who takes layering seriously."
            )
        if "crewneck" in all_text or "sweatshirt" in all_text:
            return (
                f"The <strong>{title}</strong> is Marque Légendaire's heavyweight take on the "
                "essential crewneck — a clean, oversized silhouette that carries the brand's identity "
                "without needing to shout. "
                "Built from premium fleece with drop-shoulder construction, it sits perfectly over "
                "wide-leg pants, shorts, or layered under a jacket. "
                "Elevated basics done the Legendary way."
            )
        if "goat speed" in all_text:
            return (
                f"The <strong>{title}</strong> is built for those who want their top layer to "
                "announce the pace before a word is spoken. "
                "The Goat Speed graphic brings velocity and identity to a 400GSM heavyweight boxy hoodie "
                "that stacks perfectly over tees and sits right on cargos or denim. "
                "Marque Légendaire energy — worn loud."
            )
        # Generic Marque Légendaire
        return (
            f"The <strong>{title}</strong> is a Marque Légendaire essential — heavyweight construction, "
            "clean proportions, and the brand's French-rooted identity woven into every detail. "
            "Designed to sit at the intersection of premium basics and statement streetwear, "
            "this piece earns its place in any rotation that takes quality seriously. "
            "Understated where it needs to be, bold where it counts."
        )

    # ── GOAT / GOAT Club pieces
    if "goat" in all_text:
        if "dripping" in all_text:
            return (
                f"The <strong>{title}</strong> is built heavy — 460GSM of premium fleece "
                "shaped into an oversized hoodie that defines the look before you step outside. "
                "The GOAT Club Dripping graphic does the talking, the heavyweight cotton-blend construction "
                "does the staying. "
                "This is the hoodie you wear when you want the fit to land without saying a word."
            )
        if "spray paint" in all_text or "spray painted" in all_text:
            return (
                f"The <strong>{title}</strong> channels raw creative energy through a spray-painted "
                "GOAT Club graphic on 460GSM heavyweight cotton fleece. "
                "The oversized silhouette gives the artwork the room it deserves, "
                "and the weight of the fleece means this is a piece that feels as serious as it looks. "
                "Art-inspired, street-built, GOAT certified."
            )
        if "dept" in all_text and ("tshirt" in pclass or "tee" in all_text):
            return (
                f"The <strong>{title}</strong> represents the GOAT Department — "
                "a heavyweight tee carrying the graphic identity of those who take their standards seriously. "
                "Boxy fit, dropped shoulders, and premium construction mean it sits exactly right "
                "whether you are layering or wearing it as the centrepiece. "
                "No filler. Only GOAT."
            )
        if "dept" in all_text and "jean" in all_text:
            return (
                f"The <strong>{title}</strong> is the GOAT Dept. take on premium denim — "
                "multi-pocket construction that keeps function front and center in a straight-leg silhouette "
                "built for the streets. "
                "The GOAT Dept. branding marks this as more than workwear; "
                "it is a full statement piece from waist to cuff."
            )
        if "club" in all_text and "summer" in all_text:
            return (
                f"The <strong>{title}</strong> is summer streetwear at its most deliberate — "
                "a 280GSM boxy tee built around a GOAT Club graphic that captures the season's energy "
                "without trying too hard. "
                "Oversized fit, clean drape, and the kind of heavyweight cotton that keeps its shape "
                "wash after wash. "
                "Summer in heavy rotation."
            )
        if "varsity" in all_text and "goat" in all_text:
            return (
                f"The <strong>{title}</strong> brings varsity-school energy into the GOAT Club "
                "with bold letterman-style typography on a heavyweight streetwear canvas. "
                "The oversized regular fit sits loose and effortless, "
                "and the premium cotton construction means every wear feels like a statement. "
                "School's out — GOAT Club is in."
            )
        if "lil goat" in all_text:
            return (
                f"The <strong>{title}</strong> is a clean, premium regular-fit tee carrying "
                "the Lil Goat graphic — small in name, massive in presence. "
                "Heavyweight cotton, dropped shoulders, and tight stitching make this a piece "
                "that looks sharp and holds up long-term. "
                "Simple. Sharp. GOAT."
            )
        if "the goat" in all_text and "polo" in all_text:
            return (
                f"The <strong>{title}</strong> takes the polo format and gives it a GOAT Club makeover — "
                "a boxy, relaxed silhouette that wears like a premium casual piece "
                "while still referencing the brand's streetwear roots. "
                "Everyday wear that carries quiet confidence. The GOAT way."
            )
        if "the goat" in all_text and "hoodie" in all_text:
            return (
                f"The <strong>{title}</strong> is the GOAT Club's heavyweight statement hoodie — "
                "440GSM of premium fleece shaped into an oversized build that "
                "hits every note for cold-weather rotation. "
                "The GOAT graphic sits front and center, and the construction holds its shape "
                "through every wear. "
                "Drop it into any fit and it earns its place."
            )
        # Generic GOAT
        return (
            f"The <strong>{title}</strong> carries GOAT Club energy — "
            "a graphic-forward, heavyweight piece designed for those who hold themselves "
            "to a higher standard on and off the block. "
            "Oversized proportions, premium cotton construction, and Legendary Branding "
            "craftsmanship make this a piece that earns its keep across every rotation. "
            "Built for the real ones."
        )

    # ── Specific named graphics / collections
    if "savage butterfly" in all_text:
        return (
            f"The <strong>{title}</strong> carries a graphic that speaks to transformation — "
            "the savage butterfly as a symbol of strength through change, power through beauty. "
            "Printed on heavyweight cotton in an oversized streetwear cut, it is the kind of piece "
            "that opens conversations and holds its own in any fit. "
            "Legendary Branding's identity at its most expressive."
        )
    if "ghosted" in all_text:
        return (
            f"The <strong>{title}</strong> wears the ghost graphic like it owns the room — "
            "a heavyweight tee built for those who move quietly but land hard. "
            "The Ghosted artwork is clean, iconic, and exactly the kind of statement piece "
            "that defines a rotation rather than just filling it. "
            "Premium cotton. Oversized proportions. Zero compromise."
        )
    if "world-round" in all_text or "world round" in all_text:
        return (
            f"The <strong>{title}</strong> speaks to the global reach of the Legendary Branding "
            "identity — a graphic that wraps the world in streetwear language. "
            "Heavyweight oversized construction keeps the fit serious, "
            "and the World-Round artwork makes it a conversation piece anywhere you land. "
            "Made for those who think and dress without borders."
        )
    if "denim goat" in all_text:
        return (
            f"The <strong>{title}</strong> takes the GOAT symbol and renders it in denim-blue "
            "artwork on heavyweight cotton — raw material energy meets premium streetwear execution. "
            "The oversized boxy cut gives the graphic room to breathe, "
            "and the construction keeps it structured through the wash. "
            "Denim aesthetic. Street build. GOAT identity."
        )
    if "god's country" in all_text or "gods country" in all_text:
        return (
            f"The <strong>{title}</strong> is a declaration — God's Country, worn on the chest "
            "in a heavyweight cropped boxy tee built for those who know exactly where they are from. "
            "230GSM combed cotton, dropped armholes, and a silhouette that layers seamlessly "
            "make this one of the most versatile graphic pieces in the collection. "
            "Land of the legendary."
        )
    if "bag chaser" in all_text:
        return (
            f"The <strong>{title}</strong> is a Syracuse exclusive — the Bag Chaser mentality "
            "woven into a heavyweight boxy tee that speaks directly to the hustle. "
            "Oversized proportions, premium cotton, and a graphic that communicates intent "
            "make this a piece built for those who wear their work ethic on their sleeve. "
            "Syracuse roots. Legendary standards."
        )
    if "wave runner" in all_text:
        return (
            f"The <strong>{title}</strong> rides the energy of movement — a Wave Runner "
            "graphic on a heavyweight boxy tee that captures the flow of the streets "
            "and keeps it locked into premium construction. "
            "Clean proportions, bold artwork, and Legendary Branding quality make this the "
            "piece that earns rotation before it even leaves the bag. "
            "Catch the wave."
        )
    if "mentality matters" in all_text:
        return (
            f"The <strong>{title}</strong> leads with the message — Mentality Matters, "
            "because the way you think shapes what you build and how you carry yourself. "
            "Heavyweight construction and an oversized boxy cut make this a cornerstone piece "
            "in the Legendary Branding lineup. "
            "Wear the mindset. Build the legacy."
        )
    if "mountain trek" in all_text:
        return (
            f"The <strong>{title}</strong> brings outdoor graphic energy into heavyweight "
            "streetwear territory — a Mountain Trek artwork on a boxy oversized tee "
            "that references the elevation and puts it front and center. "
            "Built for those who move between the streets and somewhere bigger. "
            "Explore everything. Compromise nothing."
        )
    if "urban safari" in all_text:
        return (
            f"The <strong>{title}</strong> is built for navigating the jungle of the everyday — "
            "an Urban Safari graphic on 280GSM heavyweight cotton that fuses adventure-inspired "
            "artwork with a clean boxy streetwear silhouette. "
            "Bold color, premium weight, and the kind of construction that keeps it looking "
            "sharp well beyond the first hundred wears. "
            "The city is the safari."
        )
    if "santa barbara" in all_text:
        return (
            f"The <strong>{title}</strong> channels the California energy of Santa Barbara "
            "through a clean, premium heavyweight piece built for those who carry the coast "
            "wherever they go. "
            "Boxy oversized fit, graphic design, and Legendary Branding construction "
            "make this a piece that slots into any rotation with zero effort. "
            "West Coast identity. Legendary execution."
        )
    if "1992 rose bowl" in all_text or "rose bowl" in all_text:
        return (
            f"The <strong>{title}</strong> references one of the most iconic moments in "
            "collegiate sporting history — the 1992 Rose Bowl — through a premium "
            "heavyweight crewneck that wears the legacy with respect. "
            "Oversized fit, rich construction, and vintage-inspired artwork make this "
            "a piece that works in any wardrobe from street to stadium. "
            "Wear the history."
        )
    if "distressed" in all_text and "legendary" in all_text:
        return (
            f"The <strong>{title}</strong> takes the classic crewneck silhouette and "
            "gives it character through a distressed treatment that looks like it has "
            "already been through something worth wearing. "
            "Heavyweight construction, oversized proportions, and the worn-in finish "
            "make this a piece that sits at the top of the rotation from day one. "
            "Legendary Branding's premium aesthetic — broken in at birth."
        )
    if "hysteria" in all_text:
        return (
            f"The <strong>{title}</strong> brings the Hysteria aesthetic to a cropped boxy "
            "tank top silhouette — bold energy, tight construction, and a sleeveless cut "
            "that was built for layering or wearing solo when the weather allows. "
            "Every detail is intentional. Every stitch is Legendary."
        )
    if "summer vibes" in all_text:
        return (
            f"The <strong>{title}</strong> is the summer staple — a waist-cropped boxy tank "
            "with Summer Vibes energy built right into the cut and the graphic. "
            "Sleeveless, lightweight, and made for those in-between moments when "
            "the weather is perfect and the fit needs to match. "
            "Cropped by design. Legendary by default."
        )
    if "athletic department" in all_text:
        return (
            f"The <strong>{title}</strong> wears the Athletic Department identity in a "
            "premium unisex tank top cut — clean, purposeful, and built for both "
            "the gym and the street without compromise. "
            "Lightweight but substantial, it is the kind of piece that transitions from "
            "a workout to a walkout without missing a beat. "
            "Performance roots. Legendary finish."
        )
    if "rottweiler" in all_text or "dawg" in all_text and "pit" in all_text:
        return (
            f"The <strong>{title}</strong> carries the Rottweiler Dawg graphic — "
            "raw, powerful, and unapologetically bold on a heavyweight oversized canvas. "
            "The drop-shoulder cut gives the artwork the space it deserves, "
            "and the premium cotton construction makes it a piece that holds its own "
            "through every rotation. "
            "Built for those who move like they mean it."
        )
    if "dawg" in all_text and "sweatpants" in all_text:
        return (
            f"The <strong>{title}</strong> brings Dawg energy into the bottom half — "
            "heavyweight sweatpants built with the same streetwear intention as every "
            "top in the Legendary Branding lineup. "
            "Comfortable enough for all-day wear, constructed well enough to hold its "
            "shape through the long run. "
            "The fit starts from the ground up."
        )
    if "adidas goat" in all_text or "adistar" in all_text:
        return (
            f"The <strong>{title}</strong> takes the GOAT Club aesthetic into Adidas-inspired "
            "territory — a premium heavyweight piece that fuses sporting heritage "
            "with Legendary Branding's street identity. "
            "Clean graphic, oversized proportions, and premium construction "
            "make this the collab-adjacent piece the rotation was missing. "
            "Sport roots. Street execution. GOAT standard."
        )
    if "coast club" in all_text:
        return (
            f"The <strong>{title}</strong> is a Legendary Coast Club piece — "
            "breezy graphic energy on a heavyweight boxy tee that captures the "
            "effortless confidence of living on the coast and dressing to match. "
            "Premium construction, oversized fit, and a graphic that tells the story "
            "without needing a caption. "
            "Legendary standards. Coastal identity."
        )
    if "land of the goated" in all_text:
        return (
            f"The <strong>{title}</strong> is a territory declaration — Land of the GOATED, "
            "worn on a heavyweight oversized tee that represents the standard you hold yourself to. "
            "Boxy proportions, premium cotton, and Legendary Branding craftsmanship "
            "make this a piece that earns its place at the top of the stack. "
            "The land is wherever you carry it."
        )
    if "stay rich" in all_text:
        return (
            f"The <strong>{title}</strong> is a mindset as much as a garment — "
            "Stay Rich, worn on a heavyweight oversized tee built by Legendary Branding "
            "for those who define wealth on their own terms. "
            "Clean graphic, premium cotton construction, and an oversized loose fit "
            "that sits effortlessly in any rotation. "
            "Wealth is the standard. Legendary is the brand."
        )
    if "chosen one" in all_text:
        return (
            f"The <strong>{title}</strong> carries the weight of identity — The Chosen One "
            "graphic on 280GSM heavyweight cotton in an oversized drop-shoulder cut "
            "that was built to stand out. "
            "This is a piece for those who know their worth and dress accordingly. "
            "Heavyweight construction. Undeniable presence."
        )
    if "shattered backboard" in all_text:
        return (
            f"The <strong>{title}</strong> references one of the most iconic moments in "
            "basketball history — the Shattered Backboard — through a graphic tee built "
            "on 280GSM heavyweight cotton in an oversized boxy silhouette. "
            "The artwork honors the moment; the construction honors the garment. "
            "Basketball culture. Legendary standards."
        )
    if "jellyfish" in all_text:
        return (
            f"The <strong>{title}</strong> brings ocean-depth energy to the streets — "
            "a Jellyfish graphic on 280GSM heavyweight cotton that puts aquatic artistry "
            "into an oversized boxy tee built for everyday rotation. "
            "Bold visual, clean proportions, and premium construction make this "
            "the piece that earns a second look every time. "
            "Deep graphic. Heavyweight build."
        )
    if "tour" in all_text and "goat club" in all_text:
        return (
            f"The <strong>{title}</strong> is GOAT Club on the road — a Tour graphic "
            "tee built in 235GSM heavyweight cotton for those who move "
            "from city to city with the same elevated standard. "
            "Boxy fit, bold print, and Legendary Branding quality mean this piece "
            "earns its place in the bag on every trip. "
            "The tour never ends."
        )
    if "brush stroke" in all_text:
        return (
            f"The <strong>{title}</strong> wears artwork the way it was meant to be worn — "
            "a bold brush stroke graphic on heavyweight cotton that brings "
            "the energy of the studio into a streetwear silhouette. "
            "Every print feels like a one-off. Every tee is built to last. "
            "Art on the body. Legendary on the label."
        )
    if "virelli" in all_text or "flower painting" in all_text:
        return (
            f"The <strong>{title}</strong> is a collaboration between streetwear and fine art — "
            "Alessandro Virelli's flower painting rendered on a 190GSM loose-fit tee "
            "that brings gallery energy to an everyday silhouette. "
            "The light-weight build keeps it breathable and easy to layer, "
            "while the artwork elevates it above any ordinary graphic tee. "
            "Art lives in the details."
        )
    if "snow wash" in all_text or "snow washed" in all_text:
        if "gradient" in all_text:
            return (
                f"The <strong>{title}</strong> wears the gradient wash finish as its signature — "
                "a subtle, sunfaded visual that builds depth into a clean heavyweight streetwear piece. "
                "The washed construction gives it a premium lived-in look from the first wear, "
                "and the oversized GOAT graphic sits perfectly on a canvas that looks like "
                "it has already seen the world. "
                "Faded on purpose. Built to last."
            )
        return (
            f"The <strong>{title}</strong> earns its identity through its finish — "
            "a snow-wash treatment on heavyweight cotton that creates a one-of-a-kind "
            "look that gets better with every wear. "
            "The oversized silhouette gives the washed graphic the space it needs, "
            "and the premium construction keeps the structure intact through the wash cycle. "
            "Vintage feel. Legendary build."
        )
    if "gradient" in all_text:
        return (
            f"The <strong>{title}</strong> uses gradient as its design language — "
            "a slow bleed of color across a heavyweight cotton canvas "
            "that makes each piece feel unique at the point of wear. "
            "Oversized, premium, and built for those who want their blank essentials "
            "to carry more visual weight than the average tee. "
            "No graphic needed. The fade is the story."
        )
    if "faith" in all_text:
        return (
            f"The <strong>{title}</strong> is a declaration of belief — the Faith "
            "graphic on a heavyweight oversized tee that carries the message "
            "with the same quiet confidence it takes to live it. "
            "Premium cotton, dropped shoulders, and clean construction "
            "make this a piece you return to time and again. "
            "Wear it with conviction."
        )
    if "permanent marker" in all_text:
        return (
            f"The <strong>{title}</strong> wears its identity in the most direct way possible — "
            "a Permanent Marker graphic that looks handwritten, raw, and impossible to erase. "
            "Printed on heavyweight cotton in an oversized streetwear cut, "
            "it is the kind of piece that announces intent without needing explanation. "
            "Bold statement. Premium build. Legendary execution."
        )
    if "fullbodyk" in all_text:
        return (
            f"The <strong>{title}</strong> is a Fullbodyk oversized graphic tee built "
            "on luxury combed cotton — a heavyweight boxy-fit piece that sits at "
            "the intersection of comfort and impact. "
            "The Fullbodyk graphic carries its own identity on a canvas "
            "constructed to hold its shape and weight through every rotation. "
            "Full body. Full quality. Legendary standard."
        )
    if "icon of the herd" in all_text:
        return (
            f"The <strong>{title}</strong> was built for those who lead — "
            "Icon of the Herd in a heavyweight cropped oversized silhouette "
            "that puts the statement front and center. "
            "250GSM combed cotton, oversized drop-shoulder cut, and clean stitching "
            "make this a piece that stands out when you want it to and holds its own "
            "when the fit speaks for itself. "
            "Lead from the front."
        )
    if "the legendary t-shirt" in all_text or title.lower() == "the legendary t-shirt":
        return (
            "The <strong>Legendary T-Shirt</strong> is the foundation — "
            "a boxy-fit heavyweight tee that carries the Legendary Branding identity "
            "in its most direct form. "
            "Built from 235GSM combed cotton with a drop-shoulder cut and clean proportions, "
            "it is the piece you build every fit around. "
            "Simple. Heavyweight. Legendary."
        )
    if "urban framework" in all_text:
        return (
            f"The <strong>{title}</strong> is part of the Urban Framework collection — "
            "a premium heavyweight piece built for those who treat their wardrobe "
            "like an architecture project: intentional, structured, and built to last. "
            "280GSM boxy tee construction, minimalist design, and Legendary Branding "
            "quality make this the blank essential that outperforms everything around it."
        )
    if "legendary 01" in all_text:
        return (
            f"The <strong>{title}</strong> is the first word in the Legendary Branding "
            "essentials language — a clean 280GSM boxy tee that carries the "
            "Legendary 01 mark without needing anything else. "
            "Drop-shoulder construction, minimalist execution, and heavyweight cotton "
            "make this the piece you come back to every time you want the fit to speak quietly "
            "but carry real weight. "
            "The original standard."
        )
    if "legendary goat standard" in all_text:
        return (
            f"The <strong>{title}</strong> defines the benchmark — the Legendary GOAT Standard "
            "on a 280GSM boxy heavyweight tee that was built to set the pace, "
            "not follow it. "
            "Drop-shoulder silhouette, clean Legendary logo, and premium cotton construction "
            "make this the piece that anchors every rotation it enters. "
            "The standard is set. The rest follows."
        )
    if "rhinestone" in all_text or "stacked straight leg" in all_text:
        return (
            f"The <strong>{title}</strong> brings hardware into the denim game — "
            "rhinestone detailing on a stacked straight-leg cut that carries "
            "the premium streetwear vision further than raw denim usually goes. "
            "Built for those who want their jeans to say as much as their tops. "
            "Statement denim. Legendary finish."
        )
    if "spliced" in all_text and "jean" in all_text:
        return (
            f"The <strong>{title}</strong> is LB's take on next-generation denim — "
            "spliced panels on a baggy streetwear silhouette that creates "
            "a construction-forward look that sits at the intersection of fashion "
            "and the block. "
            "Wear them with a heavyweight tee or a cropped hoodie. "
            "Either way, the jeans do the work."
        )
    if "baggy wide-leg" in all_text or ("wide-leg" in all_text and "denim" in all_text):
        return (
            f"The <strong>{title}</strong> is built wide and built intentionally — "
            "a baggy wide-leg denim silhouette that channels 90s street energy "
            "through a premium modern construction. "
            "The cross-stitch detailing and relaxed fit make this a bottom "
            "built for those who believe the fit starts from the ground up. "
            "Wide-leg. Wide stance. Legendary standard."
        )
    if "jogger" in all_text or "urban flare" in all_text:
        return (
            f"The <strong>{title}</strong> is designed for the full day — "
            "premium heavyweight joggers built for the street, the gym, and "
            "every moment in between. "
            "The flared cut modernizes the silhouette while the Legendary Branding "
            "construction ensures these stay in shape through the rotation. "
            "Style that moves with you."
        )
    if "lined" in all_text and "set" in all_text:
        return (
            f"The <strong>{title}</strong> is a complete look in one — "
            "a lined oversized hoodie and jogger set built by Legendary Branding "
            "for those who want the fit to be effortless from top to bottom. "
            "Matching construction, premium weight, and a silhouette designed "
            "to stack together perfectly right out of the bag. "
            "The set. The standard. The rotation."
        )
    if "fleece zip-up" in all_text or ("zip" in all_text and "fleece" in all_text):
        return (
            f"The <strong>{title}</strong> is the Legendary Branding zip-up — "
            "380GSM premium fleece in a drop-shoulder silhouette that gives "
            "the classic zip format a heavyweight streetwear upgrade. "
            "Layer it over tees, under jackets, or wear it as the top layer "
            "when the temperature drops and the fit still needs to land. "
            "Zip in. Look right."
        )
    if "button polo" in all_text or "polo collared" in all_text:
        return (
            f"The <strong>{title}</strong> is the Legendary Branding take on the "
            "collared sweatshirt — a 445GSM button-collar heavyweight piece "
            "that takes the polo format into premium fleece territory. "
            "Built for those who want the polish of a collar without giving up "
            "the weight and comfort of a streetwear sweatshirt. "
            "Elevated without effort."
        )
    if "blank heavyweight" in all_text and "hoodie" in all_text:
        return (
            f"The <strong>{title}</strong> is the ultimate foundation piece — "
            "a 460GSM blank heavyweight hoodie built from 100% cotton in an "
            "oversized silhouette that works as a blank canvas or a standalone statement. "
            "No graphic needed when the weight and the construction speak for themselves. "
            "Heavyweight. Pure. Legendary."
        )

    # ── Fallback — generic but brand-specific by garment type
    gsm = extract_gsm(tags, title)
    garment = garment_label(pclass)
    short_title = title.replace("|", "").strip()

    fallback_stories = {
        "tshirt": (
            f"The <strong>{short_title}</strong> is built the Legendary Branding way — "
            f"heavyweight {gsm} cotton in an oversized boxy silhouette "
            "that wears clean, holds its shape, and carries the brand's identity "
            "without needing to announce itself. "
            "Premium construction, drop-shoulder proportions, and a fit designed "
            "for real rotation — not a shelf."
        ),
        "hoodie": (
            f"The <strong>{short_title}</strong> is a heavyweight hoodie built for rotation — "
            f"{gsm} premium fleece in an oversized silhouette "
            "that sits exactly right whether you are layering up or wearing it solo. "
            "Legendary Branding construction ensures it holds its shape and its presence "
            "through every wear. "
            "Heavy. Clean. Built for the block."
        ),
        "sweatshirt": (
            f"The <strong>{short_title}</strong> is the Legendary Branding take on the "
            f"essential crewneck — {gsm} heavyweight fleece in an oversized silhouette "
            "that sits cleanly on everything from cargos to denim. "
            "Premium construction, clean proportions, and the brand's elevated "
            "basics identity make this a cornerstone piece for any streetwear wardrobe."
        ),
        "jacket": (
            f"The <strong>{short_title}</strong> is an outer layer built by Legendary Branding "
            "for those who refuse to let the weather dictate the fit. "
            "Premium construction, clean lines, and a silhouette designed to sit right "
            "over whatever is underneath make this the jacket that stays in heavy rotation. "
            "Layer it. Live in it."
        ),
        "shorts": (
            f"The <strong>{short_title}</strong> is built for performance and street appeal — "
            "athletic construction with moisture-management properties "
            "in a silhouette designed to move as well as it looks. "
            "Legendary Branding quality from waistband to hem. "
            "Wear them to train. Wear them to be seen."
        ),
        "pants": (
            f"The <strong>{short_title}</strong> is a Legendary Branding bottom built to "
            "anchor the fit — premium construction, clean silhouette, and "
            "the brand's elevated streetwear identity from waist to cuff. "
            "Built for those who understand that the full look starts at the bottom."
        ),
        "hat": (
            f"The <strong>{short_title}</strong> is the Legendary Branding head piece — "
            "a premium trucker hat built with clean graphics and an adjustable fit "
            "that works across every style in the rotation. "
            "Finish the fit. Carry the brand."
        ),
    }
    return fallback_stories.get(pclass, fallback_stories["tshirt"])


# ─── Feature lines ─────────────────────────────────────────────────────────────

def build_features(title: str, tags: list, pclass: str) -> list:
    features = []
    t  = title.lower()
    tl = [tag.lower() for tag in tags]
    all_text = t + " " + " ".join(tl)

    gsm = extract_gsm(tags, title)

    if pclass in ("tshirt",):
        if tag_has(tags, "boxy", "boxy fit", "boxy t shirt"):
            features.append("Boxy oversized fit for a relaxed, street-ready silhouette")
        elif tag_has(tags, "loose", "loose fit"):
            features.append("Loose fit for an effortless, easy-wearing silhouette")
        elif tag_has(tags, "cropped"):
            features.append("Waist-cropped length designed for layered looks")
        elif tag_has(tags, "regular fit"):
            features.append("Regular fit for a clean, everyday silhouette")
        else:
            features.append("Oversized fit for a premium streetwear silhouette")

        if tag_has(tags, "drop shoulder", "dropped shoulder", "dropped armhole"):
            features.append("Drop-shoulder construction for a modern, elevated drape")
        if tag_has(tags, "crew neck", "crewneck"):
            features.append("Classic crew neck collar that sits clean and flat")
        if tag_has(tags, "polo", "polo shirt"):
            features.append("Button-collar polo construction for elevated casual wear")

        if tag_has(tags, "snow wash", "snow washed", "washed"):
            features.append("Snow-wash / garment-dyed finish for a premium lived-in look")
        if tag_has(tags, "gradient", "sunfade", "faded"):
            features.append("Gradient wash finish — each piece carries unique tonal variation")
        if tag_has(tags, "camo", "camouflage"):
            features.append("All-over camo print for a bold, pattern-forward look")

        features.append(f"{gsm} heavyweight cotton for exceptional drape and durability")
        features.append("Side-seamed construction for shape retention through repeated wears")
        features.append("Pre-shrunk and ring-spun for a true-to-size fit from first wear")
        features.append("Unisex sizing fits a wide range of body types")

    elif pclass in ("hoodie",):
        if tag_has(tags, "boxy", "boxy fit"):
            features.append("Boxy oversized silhouette for a modern, structured streetwear look")
        elif tag_has(tags, "cropped"):
            features.append("Cropped hoodie length designed for layering and visual balance")
        else:
            features.append("Oversized fit with generous proportions for a premium street silhouette")

        features.append(f"{gsm} heavyweight fleece that drapes clean and holds structure through the wash")
        if tag_has(tags, "zip", "zip-up", "full zip"):
            features.append("Full zip-up closure for easy layering and ventilation control")
        else:
            features.append("Pullover hood with generous drawcord adjustment")
        features.append("Front kangaroo pocket for everyday utility and comfort")
        if tag_has(tags, "ribbed cuffs", "ribbed hem"):
            features.append("Ribbed cuffs and hem to frame the oversized body cleanly")
        features.append("Drop-shoulder construction for an authentic streetwear fit")
        features.append("Unisex design built to fit a wide range of body types")

    elif pclass in ("sweatshirt",):
        features.append(f"{gsm} heavyweight fleece for premium warmth and shape retention")
        features.append("Classic crewneck collar that sits clean across a range of necklines")
        if tag_has(tags, "drop shoulder"):
            features.append("Drop-shoulder construction for an oversized, intentional silhouette")
        else:
            features.append("Side-seamed construction for a clean, structured shape")
        if tag_has(tags, "1/4 zip", "half zip", "quarter zip"):
            features.append("1/4 zip opening for adjustable ventilation and easy layering")
        if tag_has(tags, "ribbed cuffs", "ribbed hem", "ribbed"):
            features.append("Ribbed cuffs and hem for a polished finish and shape lock")
        features.append("Pre-shrunk construction for consistent true-to-size fit over time")
        features.append("Unisex fit designed to sit comfortably across body types")

    elif pclass == "jacket":
        if tag_has(tags, "water-resistant", "water resistant", "windbreaker"):
            features.append("Water-resistant outer shell for protection from wind and light rain")
        if tag_has(tags, "packable"):
            features.append("Packable construction — folds into its own integrated pocket")
        if tag_has(tags, "half zip", "1/4 zip"):
            features.append("Half-zip pullover design for adjustable ventilation")
        if tag_has(tags, "hood", "hooded"):
            features.append("Adjustable hood for added weather protection")
        if tag_has(tags, "varsity"):
            features.append("Varsity-inspired silhouette with ribbed collar, cuffs, and hem")
        features.append("Lightweight shell construction for an easy, packable outer layer")
        features.append("Kangaroo or zip-through pockets for secure everyday carry")
        features.append("Elastic cuffs to lock warmth and keep the profile clean")
        features.append("Street-ready silhouette that layers cleanly over any base")

    elif pclass == "shorts":
        features.append("4-way stretch construction for unrestricted movement in any direction")
        features.append("Moisture-wicking and quick-dry fabric to keep you cool under pressure")
        features.append("Elastic waistband with flat drawstring for a snug, adjustable fit")
        features.append("Breathable mesh pockets — functional, bounce-free storage")
        if tag_has(tags, "upf", "upf50"):
            features.append("UPF 50+ sun protection for outdoor training and activity")
        features.append("6.5″ inseam (16.5 cm) — mid-thigh, balanced cut for any activity")
        features.append("No inner liner — streamlined construction for maximum comfort and airflow")
        features.append("Lightweight build for zero drag during training or daily wear")

    elif pclass == "pants":
        if tag_has(tags, "denim", "jeans"):
            if tag_has(tags, "baggy", "wide-leg"):
                features.append("Baggy wide-leg denim silhouette for a bold, relaxed streetwear look")
            elif tag_has(tags, "straight", "straight leg"):
                features.append("Straight-leg cut for a clean, versatile denim silhouette")
            elif tag_has(tags, "spliced"):
                features.append("Spliced panel construction for a construction-forward aesthetic")
            if tag_has(tags, "rhinestone"):
                features.append("Rhinestone hardware detailing for a premium statement finish")
            features.append("Heavy-gauge denim construction built for durability and shape retention")
            features.append("Multiple pockets including GOAT Dept. utility pockets where applicable")
        else:
            # joggers / sweatpants
            features.append("Heavyweight fleece construction for warmth and long-term shape")
            features.append("Elastic waistband with adjustable drawcord for a secure, comfortable fit")
            features.append("Tapered or flared leg depending on style — see product for specifics")
            features.append("Deep side pockets for everyday carry")
            features.append("Ribbed cuffs to lock the silhouette and keep hems in place")
            features.append("Pre-shrunk for consistent sizing through the wash")

    elif pclass == "hat":
        features.append("Adjustable snapback or strap closure for a universal, customizable fit")
        features.append("Structured foam or mesh front panels for shape retention and breathability")
        features.append("Embroidered or printed branding graphic on the front crown")
        features.append("Curved or flat brim styling — see product title for specific profile")
        features.append("Lightweight construction designed for all-day comfort")
        features.append("Unisex design that works across every style in the rotation")

    else:
        features.append(f"{gsm} premium construction for heavyweight streetwear quality")
        features.append("Legendary Branding® identity woven into every detail")
        features.append("Unisex sizing for versatile fit across body types")

    return features


# ─── Fabric & Construction lines ───────────────────────────────────────────────

def build_fabric(title: str, tags: list, pclass: str) -> list:
    fabric = []
    t  = title.lower()
    tl = [tag.lower() for tag in tags]
    all_text = t + " " + " ".join(tl)
    gsm = extract_gsm(tags, title)

    if pclass in ("tshirt", "hoodie", "sweatshirt"):
        if tag_has(tags, "100% cotton", "cotton"):
            fabric.append(f"100% ring-spun cotton — {gsm} weight for premium feel and durability")
        elif tag_has(tags, "cotton polyester", "cotton blend"):
            fabric.append(f"Cotton-polyester blend — {gsm} weight balancing comfort and structure")
        elif tag_has(tags, "190gsm", "190 gsm"):
            fabric.append("190GSM lightweight combed cotton for a softer, breathable hand feel")
        else:
            fabric.append(f"Heavyweight {gsm} combed cotton for exceptional drape and density")

        if tag_has(tags, "fleece"):
            fabric.append("Brushed fleece interior for a warm, soft feel against the skin")
        fabric.append("Side-seamed construction for shape retention and a cleaner fit profile")
        fabric.append("Pre-shrunk finish for true-to-size fit from first wear through repeated washes")
        if tag_has(tags, "ribbed cuffs", "ribbed hem", "ribbed"):
            fabric.append("Ribbed knit cuffs and hem for a structured, premium finish")
        if tag_has(tags, "snow wash", "washed", "garment dyed"):
            fabric.append("Garment-washed / snow-wash treatment applied post-construction for authentic vintage character")
        fabric.append("Durable reinforced stitching designed for long-term, high-frequency wear")

    elif pclass == "jacket":
        if tag_has(tags, "micro poplin", "polyester"):
            fabric.append("100% polyester micro poplin shell — lightweight, smooth, and water-resistant")
        else:
            fabric.append(f"{gsm} premium outer shell fabric for weather resistance and street-ready structure")
        fabric.append("Elastic cuffs and adjustable drawcord hem for a secure, streamlined fit")
        fabric.append("Hidden or external zip pocket construction for secure carry")
        fabric.append("Packable or structured build depending on style — see product title")
        fabric.append("Durable stitching and hardware for long-term wear through heavy rotation")

    elif pclass == "shorts":
        fabric.append("91% recycled polyester / 9% spandex — 4-way stretch performance blend")
        fabric.append("5.13 oz/yd² lightweight build — minimal drag, maximum freedom of movement")
        fabric.append("Moisture-wicking and quick-dry treatment for high-performance training")
        fabric.append("UPF 50+ construction for outdoor sun protection built into the fabric")
        fabric.append("Breathable mesh pocket lining for functional, bounce-free carry")
        fabric.append("Elastic waistband with flat drawstring for a clean, adjustable fit")

    elif pclass == "pants":
        if tag_has(tags, "denim", "jeans"):
            fabric.append("Premium heavyweight denim construction for durability and shape retention")
            fabric.append("Structured waistband with functional button and zip fly")
            fabric.append("Cotton-blend denim for a comfortable, break-in-ready build")
            if tag_has(tags, "rhinestone"):
                fabric.append("Rhinestone hardware detailing applied post-construction for statement finish")
            fabric.append("Reinforced pocket seams for long-term carry integrity")
        else:
            fabric.append(f"Heavyweight {gsm} fleece blend for warmth, weight, and shape retention")
            fabric.append("Brushed interior for softness and insulation through cold-weather rotation")
            fabric.append("Elastic waistband construction with adjustable drawcord")
            fabric.append("Ribbed cuff construction to lock silhouette and reduce ankle bunching")
            fabric.append("Pre-shrunk and finished for consistent sizing across wears and washes")

    elif pclass == "hat":
        fabric.append("Structured foam front panels for crown shape retention and all-day wear")
        fabric.append("Breathable mesh rear panels for ventilation and lightweight comfort")
        fabric.append("Adjustable plastic snapback or fabric strap closure for custom fit")
        fabric.append("Pre-curved or flat brim — see product title for specific profile")
        fabric.append("Embroidered branding stitched directly into the front crown for durability")

    else:
        fabric.append(f"{gsm} premium fabric construction for heavyweight quality")
        fabric.append("Reinforced stitching for long-term wear and shape retention")

    return fabric


# ─── Care Instructions (standard by garment type) ─────────────────────────────

CARE_STANDARD = (
    "Wash inside out in cold water on a gentle cycle with mild detergent<br>"
    "Do not bleach, soak, rub, or wring<br>"
    "Wash with like colored garments to protect both fabric and print<br>"
    "Hang dry and avoid direct sunlight when possible<br>"
    "Iron, steam, or tumble dry at low temperature (max 30&#8451; or 90&#8457;)"
)

CARE_DENIM = (
    "Machine wash cold, inside out, with like colors<br>"
    "Gentle cycle — do not wring or twist<br>"
    "Do not bleach<br>"
    "Hang dry to preserve denim weight and shape<br>"
    "Iron on low if needed, inside out"
)

CARE_SHORTS = (
    "Machine wash cold with like colors<br>"
    "Gentle cycle — do not wring or twist<br>"
    "Do not bleach or use fabric softener<br>"
    "Tumble dry low or hang dry<br>"
    "Do not iron directly over mesh or performance fabric"
)

CARE_HAT = (
    "Spot clean with a soft damp cloth and mild soap<br>"
    "Do not machine wash or tumble dry<br>"
    "Reshape brim while damp and allow to air dry<br>"
    "Avoid prolonged exposure to direct sunlight to preserve color"
)


def get_care(pclass: str, tags: list) -> str:
    if pclass == "hat":
        return CARE_HAT
    if pclass == "shorts":
        return CARE_SHORTS
    if pclass == "pants" and tag_has(tags, "denim", "jeans"):
        return CARE_DENIM
    return CARE_STANDARD


# ─── Size table router ─────────────────────────────────────────────────────────

def get_size_table(pclass: str) -> str:
    if pclass == "tshirt":
        return tshirt_size_table()
    elif pclass in ("hoodie", "sweatshirt", "jacket"):
        return sweat_size_table()
    elif pclass == "shorts":
        return shorts_size_table()
    elif pclass == "pants":
        return pants_size_table()
    elif pclass == "hat":
        return hat_size_table()
    return tshirt_size_table()


# ─── Brand / Shipping closing ──────────────────────────────────────────────────

def generate_brand_close(title: str, tags: list, pclass: str) -> str:
    """
    Returns ONE product-specific closing sentence to follow the mandatory
    Legendary Branding® tagline, with NO free-shipping mentions.
    """
    t = title.lower()
    all_text = t + " " + " ".join(tags).lower()

    if "champion" in all_text:
        extra = "A collaboration built on shared standards — heavyweight outerwear and streetwear that performs every time you reach for it"
    elif "neverdy" in all_text:
        extra = "The Neverdy collection brings raw, graphic-forward energy into the Legendary Branding lineup for those who refuse to be ordinary"
    elif "marque" in all_text or "légendaire" in all_text:
        extra = "Marque Légendaire represents the elevated tier of the brand — premium construction, refined aesthetic, and the same heavyweight DNA"
    elif "goat" in all_text and "club" in all_text:
        extra = "The GOAT Club line is built for those who hold themselves to the highest standard in everything they do — including what they wear"
    elif "santa barbara" in all_text:
        extra = "This piece carries the California identity that the Santa Barbara collection was built to honor"
    elif "rose bowl" in all_text or "1992" in all_text:
        extra = "The 1992 Rose Bowl collection honors a legendary moment in athletic history through premium streetwear construction"
    elif "urban framework" in all_text:
        extra = "Urban Framework pieces are the structural foundation of the Legendary Branding wardrobe — built to anchor every fit"
    elif pclass == "hat":
        extra = "Every hat is finished with the same attention to detail that goes into every garment in the Legendary Branding lineup"
    elif pclass in ("pants",) and tag_has(tags, "denim", "jeans"):
        extra = "Premium denim built by Legendary Branding to carry the same quality standards as every heavyweight piece in the collection"
    elif pclass == "shorts":
        extra = "Performance and street appeal in a single garment — built to move with you from training to everyday rotation"
    elif pclass in ("hoodie", "sweatshirt"):
        extra = "Every stitch is built to hold up through the long rotation that heavyweight streetwear deserves"
    else:
        extra = "Every garment in the Legendary Branding catalog is crafted to the same standard — built to be worn on repeat, never retired early"

    return extra


# ─── Full HTML builder ─────────────────────────────────────────────────────────

def build_description(product: dict) -> str:
    title    = product.get("title", "")
    tags     = product.get("tags", [])
    pclass   = classify_product(product)
    gsm      = extract_gsm(tags, title)
    garment  = garment_label(pclass)

    h2_style      = SECTION_H2
    title_h2_style = TITLE_H2

    # ── Title block
    title_line = f'<h2 {title_h2_style}>{title} | {gsm} · {garment}</h2>'

    # ── Selling story
    story = generate_selling_story(title, tags, pclass)
    story_block = (
        f'<p style="text-align: center; max-width: 680px; margin: 0 auto 16px auto;">'
        f'{story}</p>'
    )

    # ── Features
    features = build_features(title, tags, pclass)
    features_block = (
        f'<h2 {h2_style}>Features</h2>\n'
        f'<p style="text-align: center; line-height: 1.8;">'
        + "<br>".join(features)
        + "</p>"
    )

    # ── Fabric & Construction
    fabric = build_fabric(title, tags, pclass)
    fabric_block = (
        f'<h2 {h2_style}>Fabric &amp; Construction</h2>\n'
        f'<p style="text-align: center; line-height: 1.8;">'
        + "<br>".join(fabric)
        + "</p>"
    )

    # ── Care
    care_block = (
        f'<h2 {h2_style}>Care Instructions</h2>\n'
        f'<p style="text-align: center; line-height: 1.8;">{get_care(pclass, tags)}</p>'
    )

    # ── Size Guide
    size_table = get_size_table(pclass)
    size_block = f'<h2 {h2_style}>Size Guide</h2>\n{size_table}'

    # ── Shipping & Brand (CORRECT format per brand rules)
    brand_extra = generate_brand_close(title, tags, pclass)
    brand_block = (
        f'<h2 {h2_style}>Shipping &amp; Brand</h2>\n'
        f'<p style="text-align: center; max-width: 680px; margin: 0 auto;">'
        f'Designed by <strong>Legendary Branding\u00ae</strong> for heavyweight streetwear '
        f'you actually want to wear on repeat. {brand_extra}. '
        f'Ships from our fulfillment partners with tracking provided.</p>'
    )

    return "\n".join([
        title_line,
        story_block,
        features_block,
        fabric_block,
        care_block,
        size_block,
        brand_block,
    ])


# ─── Update mutation ───────────────────────────────────────────────────────────

UPDATE_MUTATION = """
mutation UpdateProductDescription($id: ID!, $descriptionHtml: String!) {
  productUpdate(product: { id: $id, descriptionHtml: $descriptionHtml }) {
    product {
      id
      title
      descriptionHtml
    }
    userErrors {
      field
      message
    }
  }
}
"""


def push_update(product_id: str, body_html: str) -> bool:
    variables = {
        "id":            product_id,
        "descriptionHtml": body_html,
    }
    data   = gql_request(UPDATE_MUTATION, variables)
    result = data["data"]["productUpdate"]
    errors = result.get("userErrors", [])
    if errors:
        log.error(f"  userErrors: {errors}")
        return False
    return True


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Legendary Branding Product Description Updater")
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually push updates to Shopify (default: dry run only)"
    )
    parser.add_argument(
        "--preview", type=int, default=3,
        help="Number of products to preview in dry-run mode (default: 3)"
    )
    parser.add_argument(
        "--product-id", type=str, default=None,
        help="Update a single product by its numeric Shopify ID (e.g. 8774531121305)"
    )
    args = parser.parse_args()

    dry_run = not args.execute
    mode_label = "DRY RUN" if dry_run else "LIVE EXECUTE"

    log.info(f"{'='*60}")
    log.info(f"Legendary Branding Product Description Updater — {mode_label}")
    log.info(f"Started: {datetime.now().isoformat()}")
    log.info(f"{'='*60}")

    # ── Fetch all products
    products = fetch_all_products()
    log.info(f"Total products fetched: {len(products)}")

    # ── Filter to single product if requested
    if args.product_id:
        gid = f"gid://shopify/Product/{args.product_id}"
        products = [p for p in products if p["id"] == gid]
        if not products:
            log.error(f"Product ID {args.product_id} not found.")
            sys.exit(1)
        log.info(f"Single-product mode: {products[0]['title']}")

    # ── Backup originals before any changes
    if not dry_run:
        log.info(f"Saving original descriptions backup to {BACKUP_PATH}")
        backup = {p["id"]: {"title": p["title"], "bodyHtml": p.get("bodyHtml", "")} for p in products}
        with open(BACKUP_PATH, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=2, ensure_ascii=False)
        log.info("Backup saved.")
    else:
        log.info("DRY RUN — skipping backup (no changes will be made).")

    # ── Process products
    success_count = 0
    fail_count    = 0
    preview_shown = 0

    # Already-updated products — skip to avoid duplicate writes
    ALREADY_UPDATED = {
        "gid://shopify/Product/8774531121305",  # Legendary GOAT Standard Boxy T-Shirt
    }

    for i, product in enumerate(products):
        pid   = product["id"]
        title = product["title"]
        log.info(f"\n[{i+1}/{len(products)}] {title}")
        log.info(f"  ID: {pid}")

        if pid in ALREADY_UPDATED and not dry_run:
            log.info(f"  SKIPPED — already updated in prior run")
            success_count += 1
            continue

        try:
            new_html = build_description(product)
        except Exception as e:
            log.error(f"  FAILED to generate description: {e}")
            fail_count += 1
            continue

        if dry_run:
            if preview_shown < args.preview:
                print(f"\n{'─'*70}")
                print(f"PREVIEW — {title}")
                print(f"{'─'*70}")
                print(new_html[:1500])
                print(f"  ... [{len(new_html)} chars total]")
                preview_shown += 1
            else:
                log.info(f"  [DRY RUN] Would update — {len(new_html)} chars generated")
            success_count += 1
        else:
            log.info(f"  Pushing update ({len(new_html)} chars)...")
            try:
                ok = push_update(pid, new_html)
                if ok:
                    log.info(f"  SUCCESS")
                    success_count += 1
                else:
                    log.error(f"  FAILED (userErrors returned)")
                    fail_count += 1
            except Exception as e:
                log.error(f"  FAILED — exception: {e}")
                fail_count += 1

            # Rate-limit courtesy pause
            time.sleep(0.5)

    # ── Summary
    log.info(f"\n{'='*60}")
    log.info(f"Run complete — {mode_label}")
    log.info(f"Total products:  {len(products)}")
    log.info(f"Success:         {success_count}")
    log.info(f"Failed:          {fail_count}")
    log.info(f"Finished: {datetime.now().isoformat()}")
    log.info(f"{'='*60}")


if __name__ == "__main__":
    main()
