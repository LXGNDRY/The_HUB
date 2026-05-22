#!/usr/bin/env python3
"""Pull all shipping zones and rates in full detail."""
import os, requests, json

SHOP = "lngndny.myshopify.com"
API_VERSION = "2024-01"
TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
H = {"X-Shopify-Access-Token": TOKEN}

resp = requests.get(f"https://{SHOP}/admin/api/{API_VERSION}/shipping_zones.json", headers=H)
zones = resp.json().get("shipping_zones", [])
print(f"Total shipping zones: {len(zones)}\n")

for z in zones:
    print(f"{'─'*60}")
    print(f"Zone: {z['name']}  (id: {z['id']})")

    # Countries
    countries = z.get("countries", [])
    if countries:
        names = []
        for c in countries:
            provinces = c.get("provinces", [])
            if provinces:
                prov_names = [p["name"] for p in provinces]
                names.append(f"{c['name']} [{', '.join(prov_names)}]")
            else:
                names.append(c["name"])
        print(f"  Countries: {', '.join(names)}")
    else:
        print(f"  Countries: (none)")

    # Price-based
    pbr = z.get("price_based_shipping_rates", [])
    if pbr:
        print(f"  Price-based rates ({len(pbr)}):")
        for r in pbr:
            price = float(r.get("price", 0))
            min_s = r.get("min_order_subtotal") or "0"
            max_s = r.get("max_order_subtotal") or "∞"
            free = "(FREE SHIPPING)" if price == 0 else ""
            print(f"    • '{r['name']}': ${price:.2f} {free}  order subtotal: ${min_s}–${max_s}")
    else:
        print(f"  Price-based rates: (none)")

    # Weight-based
    wbr = z.get("weight_based_shipping_rates", [])
    if wbr:
        print(f"  Weight-based rates ({len(wbr)}):")
        for r in wbr:
            print(f"    • '{r['name']}': ${float(r.get('price',0)):.2f}  weight: {r.get('weight_low',0)}–{r.get('weight_high','∞')} kg")
    else:
        print(f"  Weight-based rates: (none)")

    # Carrier-calculated
    csr = z.get("carrier_shipping_rates", [])
    if csr:
        print(f"  Carrier-calculated rates ({len(csr)}):")
        for r in csr:
            print(f"    • '{r['name']}' — service_id: {r.get('carrier_service_id')}  flat_modifier: {r.get('flat_modifier')}  pct_modifier: {r.get('percent_modifier')}")
    else:
        print(f"  Carrier-calculated rates: (none)")

    print()

# Dump raw for full inspection
with open("/tmp/shipping_zones_raw.json", "w") as f:
    json.dump(zones, f, indent=2)
print("Raw JSON saved to /tmp/shipping_zones_raw.json")
