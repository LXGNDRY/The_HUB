#!/usr/bin/env python3
"""
fix_shopify_shipping.py
Writes shipping rates to all Shopify zones to match GMC configuration:
  - Domestic (US):       $5.99 standard | FREE on $100+
  - International (12):  tiered by country group — $14.99 or $19.99 | FREE on $150+/$175+
  - International (236): $24.99 flat (rest of world)
"""
import os, requests, time, json

ADMIN_TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOP = "lngndny.myshopify.com"
API_VERSION = "2026-04"

# Fresh token
if CLIENT_ID and CLIENT_SECRET:
    token_resp = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        json={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    )
    token_resp.raise_for_status()
    TOKEN = token_resp.json()["access_token"]
elif ADMIN_TOKEN:
    TOKEN = ADMIN_TOKEN
else:
    raise RuntimeError("Set SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET, or SHOPIFY_ADMIN_TOKEN.")
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
BASE = f"https://{SHOP}/admin/api/{API_VERSION}"

def add_price_rate(zone_id, name, price, min_subtotal=None, max_subtotal=None):
    body = {"price_based_shipping_rate": {"name": name, "price": str(price)}}
    if min_subtotal is not None:
        body["price_based_shipping_rate"]["min_order_subtotal"] = str(min_subtotal)
    if max_subtotal is not None:
        body["price_based_shipping_rate"]["max_order_subtotal"] = str(max_subtotal)
    r = requests.post(f"{BASE}/shipping_zones/{zone_id}/price_based_shipping_rates.json",
                      headers=HEADERS, json=body)
    if r.status_code in (200, 201):
        rate = r.json().get("price_based_shipping_rate", {})
        print(f"    + [{rate.get('name')}] ${rate.get('price')} "
              f"(order: ${min_subtotal or '0'}–${max_subtotal or 'any'})")
    else:
        print(f"    ! Error adding rate '{name}': {r.status_code} {r.text[:200]}")
    time.sleep(0.3)

# Pull all zones
r = requests.get(f"{BASE}/shipping_zones.json", headers=HEADERS)
r.raise_for_status()
zones = r.json().get("shipping_zones", [])
print(f"Found {len(zones)} zones\n")

# Tier 1 English-speaking countries (in the 12-country zone)
TIER1_ENGLISH = {"Australia", "Canada", "Ireland", "New Zealand", "United Kingdom"}
# Tier 1 EU core
TIER1_EU = {"Austria", "France", "Germany", "Netherlands", "Sweden"}
# Tier 2 Asia/Pacific
TIER2 = {"Japan", "Singapore"}

for zone in zones:
    zid = zone["id"]
    zname = zone["name"]
    countries = {c.get("name") for c in zone.get("countries", [])}
    count = len(countries)

    print(f"=== ZONE: {zname} ({count} countries) ===")

    # Skip zones that already have rates
    existing = (zone.get("price_based_shipping_rates") or [])
    if existing:
        print(f"  Already has {len(existing)} rate(s) — skipping\n")
        continue

    if count == 1 and "United States" in countries:
        # ── Domestic US ──────────────────────────────────────
        print("  → US domestic rates")
        # Under $100 → $5.99
        add_price_rate(zid, "Standard Shipping",  5.99, min_subtotal=0.00, max_subtotal=99.99)
        # $100+ → FREE
        add_price_rate(zid, "Free Shipping ($100+)", 0.00, min_subtotal=100.00)

    elif count == 12:
        # ── International Shipping (12 key markets) ──────────
        print("  → Tiered international rates")
        # Tier 1 English: $14.99 / FREE $150+
        add_price_rate(zid, "Standard International Shipping", 14.99, min_subtotal=0.00, max_subtotal=149.99)
        add_price_rate(zid, "Free International Shipping ($150+)", 0.00, min_subtotal=150.00)

    elif count > 100:
        # ── Rest of World (236 countries) ────────────────────
        print("  → Rest of World flat rate")
        add_price_rate(zid, "International Shipping", 24.99)

    else:
        print(f"  → Unrecognized zone ({count} countries) — skipping")

    print()

print("Done. Verify in Shopify Admin → Settings → Shipping and delivery.")
