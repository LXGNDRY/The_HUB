"""
gmc_shipping_report.py — read-only Shopify vs GMC shipping comparison + Simprosys/feed inventory.

Uses Merchant API v1. Writes outputs/gmc_shipping_report.json and prints a summary.
Env: GCP_SA_KEY (or GCP_SA_KEY_JSON), SHOPIFY_CLIENT_ID/SECRET or SHOPIFY_ADMIN_TOKEN.
"""
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules import merchant_api as gmc  # noqa: E402

SHOP = os.environ.get("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
API_VERSION = "2026-04"


def shopify_headers() -> dict:
    cid, secret = os.environ.get("SHOPIFY_CLIENT_ID"), os.environ.get("SHOPIFY_CLIENT_SECRET")
    if cid and secret:
        r = requests.post(f"https://{SHOP}/admin/oauth/access_token", timeout=30,
                          json={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret})
        if r.status_code == 200:
            return {"X-Shopify-Access-Token": r.json()["access_token"]}
    token = os.environ.get("SHOPIFY_ADMIN_TOKEN")
    if not token:
        sys.exit("ERROR: no Shopify credentials available.")
    return {"X-Shopify-Access-Token": token}


def shopify_countries() -> dict:
    """country code -> {zone, free, min_paid} from Shopify shipping zones."""
    r = requests.get(f"https://{SHOP}/admin/api/{API_VERSION}/shipping_zones.json",
                     headers=shopify_headers(), timeout=60)
    r.raise_for_status()
    out = {}
    for zone in r.json().get("shipping_zones", []):
        rates = zone.get("price_based_shipping_rates", []) + zone.get("weight_based_shipping_rates", [])
        prices = [float(x.get("price", 0)) for x in rates]
        info = {
            "zone": zone.get("name"),
            "free": any(p == 0 for p in prices),
            "min_paid": min((p for p in prices if p > 0), default=None),
            "carrier_calculated": bool(zone.get("carrier_shipping_rate_providers")),
        }
        for c in zone.get("countries", []):
            if c.get("code") and c["code"] != "*":
                out[c["code"]] = info
    return out


def gmc_countries(settings: dict) -> dict:
    """country code -> list of {service, active, rate, currency} from GMC shipping settings."""
    out = {}
    for svc in settings.get("services", []):
        rate_groups = svc.get("rateGroups", [])
        rate = gmc.flat_rate(rate_groups[0]) if rate_groups else None
        for code in svc.get("deliveryCountries", []):
            out.setdefault(code, []).append({
                "service": svc.get("serviceName"), "active": svc.get("active", False),
                "rate": rate, "currency": svc.get("currencyCode"),
            })
    return out


def compare(shop: dict, g: dict) -> dict:
    only_shopify = sorted(set(shop) - set(g))
    only_gmc = sorted(set(g) - set(shop))
    mismatches = []
    for code in sorted(set(shop) & set(g)):
        rates = {s["rate"] for s in g[code] if s["active"]}
        s = shop[code]
        if s["free"] and "0.00" not in rates:
            mismatches.append({"country": code, "issue": "Shopify free, GMC has no free service",
                               "shopify": s, "gmc": g[code]})
        elif s["min_paid"] is not None and not s["free"] and rates and f"{s['min_paid']:.2f}" not in rates:
            mismatches.append({"country": code, "issue": "paid rate differs",
                               "shopify": s, "gmc": g[code]})
    return {"missing_in_gmc": only_shopify, "not_in_shopify": only_gmc, "rate_mismatches": mismatches}


def feed_inventory() -> list:
    rows = []
    for ds in gmc.data_sources():
        primary = ds.get("primaryProductDataSource", {})
        supp = ds.get("supplementalProductDataSource", {})
        rows.append({
            "name": ds.get("displayName"), "id": ds.get("dataSourceId"), "input": ds.get("input"),
            "kind": "primary" if primary else "supplemental" if supp else "other",
            "countries": primary.get("countries"), "feedLabel": primary.get("feedLabel") or supp.get("feedLabel"),
            "file": ds.get("fileInput", {}).get("fileName"),
        })
    return rows


def shipping_issue_summary() -> dict:
    """Count item-level issues mentioning shipping across all products."""
    counts, total = {}, 0
    for p in gmc.products():
        total += 1
        for i in p.get("productStatus", {}).get("itemLevelIssues", []):
            text = f"{i.get('code', '')} {i.get('description', '')}".lower()
            if "shipping" in text or "delivery" in text:
                key = f"{i.get('severity')}: {i.get('description') or i.get('code')}"
                counts[key] = counts.get(key, 0) + 1
    return {"products_scanned": total, "shipping_issues": counts}


def section(name: str, fn):
    try:
        return fn()
    except Exception as e:  # report and continue so one failing endpoint doesn't hide the rest
        print(f"  ERROR in {name}: {e}")
        return {"error": str(e)}


def main():
    report = {}
    print("=== GMC shipping settings (Merchant API v1) ===")
    settings = section("shipping_settings", gmc.shipping_settings)
    g = {} if "error" in settings else gmc_countries(settings)
    print(f"  GMC services: {len(settings.get('services', []))}, countries: {len(g)}")
    print("=== Shopify shipping zones ===")
    shop = section("shopify_zones", shopify_countries)
    shop = {} if "error" in shop else shop
    print(f"  Shopify countries: {len(shop)}")
    if shop and g:
        report["comparison"] = compare(shop, g)
        c = report["comparison"]
        print(f"  In Shopify, missing in GMC ({len(c['missing_in_gmc'])}): {c['missing_in_gmc']}")
        print(f"  In GMC, not in Shopify ({len(c['not_in_shopify'])}): {c['not_in_shopify']}")
        print(f"  Rate mismatches ({len(c['rate_mismatches'])}):")
        for m in c["rate_mismatches"]:
            print(f"    {m['country']}: {m['issue']}")
    report["gmc_countries"] = g
    report["shopify_countries"] = shop
    print("=== Data sources / feeds (Simprosys etc.) ===")
    report["data_sources"] = section("data_sources", feed_inventory)
    if isinstance(report["data_sources"], list):
        for row in report["data_sources"]:
            print(f"  [{row['kind']}] {row['name']} | input={row['input']} | label={row['feedLabel']} "
                  f"| countries={row['countries']}")
    print("=== Product shipping issues ===")
    report["shipping_issues"] = section("products", shipping_issue_summary)
    print(f"  {report['shipping_issues']}")
    os.makedirs("outputs", exist_ok=True)
    with open("outputs/gmc_shipping_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print("Saved outputs/gmc_shipping_report.json")


if __name__ == "__main__":
    main()
