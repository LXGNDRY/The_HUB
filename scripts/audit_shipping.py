#!/usr/bin/env python3
"""
audit_shipping.py
Pulls all shipping zones, rates, carrier services, locations, and
fulfillment services from the Shopify Admin API and prints a full audit.
"""

import os, json, requests, time

SHOP = "lngndny.myshopify.com"
API_VERSION = "2024-01"
TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

def get(path, params=None):
    resp = requests.get(f"https://{SHOP}/admin/api/{API_VERSION}/{path}", headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ── Locations ────────────────────────────────────────────────
section("LOCATIONS")
locs = get("locations.json", {"limit": 50})
for loc in locs.get("locations", []):
    active = "✓ ACTIVE" if loc.get("active") else "✗ INACTIVE"
    primary = " [PRIMARY]" if loc.get("legacy") else ""
    print(f"  [{loc['id']}] {loc['name']}{primary} — {active}")
    print(f"    Address: {loc.get('address1','')} {loc.get('city','')} {loc.get('province','')} {loc.get('country','')} {loc.get('zip','')}")
    print(f"    Fulfills online orders: {loc.get('fulfills_online_orders', False)}")
    print()

# ── Shipping Zones ───────────────────────────────────────────
section("SHIPPING ZONES & RATES")
zones = get("shipping_zones.json")
for zone in zones.get("shipping_zones", []):
    print(f"\n  Zone: {zone['name']} (id: {zone['id']})")

    # Countries in this zone
    countries = zone.get("countries", [])
    country_names = [f"{c.get('name')} ({c.get('code')})" for c in countries]
    if country_names:
        print(f"    Countries: {', '.join(country_names)}")
    else:
        print(f"    Countries: (none)")

    # Price-based rates
    price_rates = zone.get("price_based_shipping_rates", [])
    if price_rates:
        print(f"    Price-based rates:")
        for r in price_rates:
            min_price = r.get("min_order_subtotal") or "0"
            max_price = r.get("max_order_subtotal") or "∞"
            price = float(r.get("price", 0))
            print(f"      '{r['name']}': ${price:.2f}  (order subtotal ${min_price}–${max_price})")
    else:
        print(f"    Price-based rates: (none)")

    # Weight-based rates
    weight_rates = zone.get("weight_based_shipping_rates", [])
    if weight_rates:
        print(f"    Weight-based rates:")
        for r in weight_rates:
            print(f"      '{r['name']}': ${float(r.get('price',0)):.2f}  ({r.get('weight_low',0)}–{r.get('weight_high','∞')} kg)")
    else:
        print(f"    Weight-based rates: (none)")

    # Carrier-calculated rates
    carrier_rates = zone.get("carrier_shipping_rates", [])
    if carrier_rates:
        print(f"    Carrier-calculated rates:")
        for r in carrier_rates:
            print(f"      '{r['name']}' — carrier: {r.get('carrier_service_id')}  flat_modifier: {r.get('flat_modifier')}  percent_modifier: {r.get('percent_modifier')}")
    else:
        print(f"    Carrier-calculated rates: (none)")

# ── Carrier Services ─────────────────────────────────────────
section("CARRIER SERVICES (3PL / custom)")
try:
    carriers = get("carrier_services.json")
    svcs = carriers.get("carrier_services", [])
    if svcs:
        for c in svcs:
            print(f"  [{c['id']}] {c['name']} — active: {c.get('active')}  callback: {c.get('callback_url')}")
    else:
        print("  (none configured)")
except Exception as e:
    print(f"  Error: {e}")

# ── Fulfillment Services ─────────────────────────────────────
section("FULFILLMENT SERVICES")
try:
    fs = get("fulfillment_services.json", {"scope": "all"})
    for f in fs.get("fulfillment_services", []):
        print(f"  [{f['id']}] {f['name']} — type: {f.get('fulfillment_orders_opt_in')}  handle: {f.get('handle')}")
        print(f"    location_id: {f.get('location_id')}  requires_shipping_method: {f.get('requires_shipping_method')}")
except Exception as e:
    print(f"  Error: {e}")

# ── Markets / International ──────────────────────────────────
section("SHOPIFY MARKETS (international)")
try:
    markets = get("markets.json")
    for m in markets.get("markets", []):
        enabled = "✓ ENABLED" if m.get("enabled") else "✗ DISABLED"
        primary = " [PRIMARY]" if m.get("primary") else ""
        print(f"  {m['name']}{primary} — {enabled}  (id: {m['id']})")
except Exception as e:
    print(f"  Error: {e}")

print("\n\nAudit complete.")
