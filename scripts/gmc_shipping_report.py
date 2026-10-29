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


def _tier(rate: dict) -> dict:
    """One Shopify rate with its order-subtotal / weight conditions kept."""
    def num(v):
        return float(v) if v not in (None, "") else None
    return {"name": rate.get("name"), "price": float(rate.get("price", 0)),
            "min_subtotal": num(rate.get("min_order_subtotal")), "max_subtotal": num(rate.get("max_order_subtotal")),
            "min_weight": num(rate.get("weight_low")), "max_weight": num(rate.get("weight_high"))}


def _shipping_class(tiers: list) -> dict:
    """free_always: a $0 tier with no conditions. free_over: $0 tier gated by a minimum, plus paid tiers."""
    free = [t for t in tiers if t["price"] == 0]
    paid = [t["price"] for t in tiers if t["price"] > 0]
    unconditional = [t for t in free if not t["min_subtotal"] and not t["min_weight"]]
    thresholds = [t["min_subtotal"] for t in free if t["min_subtotal"]]
    return {
        "free_always": bool(unconditional) and not paid,
        "free_over": min(thresholds) if thresholds and paid else None,
        "min_paid": min(paid, default=None),
    }


def shopify_countries() -> dict:
    """country code -> {zone, tiers, free_always, free_over, min_paid} from Shopify shipping zones."""
    r = requests.get(f"https://{SHOP}/admin/api/{API_VERSION}/shipping_zones.json",
                     headers=shopify_headers(), timeout=60)
    r.raise_for_status()
    out = {}
    for zone in r.json().get("shipping_zones", []):
        rates = zone.get("price_based_shipping_rates", []) + zone.get("weight_based_shipping_rates", [])
        tiers = [_tier(x) for x in rates]
        info = {"zone": zone.get("name"), "tiers": tiers, **_shipping_class(tiers),
                "carrier_calculated": bool(zone.get("carrier_shipping_rate_providers"))}
        for c in zone.get("countries", []):
            if c.get("code") and c["code"] != "*":
                out[c["code"]] = info
    return out


def gmc_countries(settings: dict) -> tuple:
    """(active, inactive_only): country -> [{service, rate, currency}] for active services; countries with
    only inactive services."""
    active, inactive = {}, {}
    for svc in settings.get("services", []):
        rate_groups = svc.get("rateGroups", [])
        rate = gmc.flat_rate(rate_groups[0]) if rate_groups else None
        if rate == "NO_SHIPPING":
            continue
        target = active if svc.get("active", False) else inactive
        for code in svc.get("deliveryCountries", []):
            target.setdefault(code, []).append({"service": svc.get("serviceName"), "rate": rate,
                                                "currency": svc.get("currencyCode")})
    return active, sorted(set(inactive) - set(active))


def _mismatch(code: str, s: dict, g: list):
    rates = {x["rate"] for x in g}
    if s["free_always"] and "0.00" not in rates:
        return {"country": code, "issue": "Shopify free, GMC has no free service"}
    if s["free_over"] is not None and rates == {"0.00"}:
        return {"country": code, "issue": f"GMC free for all orders; Shopify charges "
                                          f"${s['min_paid']:.2f} below ${s['free_over']:.2f}"}
    if not s["free_always"] and s["free_over"] is None and s["min_paid"] is not None \
            and f"{s['min_paid']:.2f}" not in rates:
        return {"country": code, "issue": f"paid rate differs (Shopify ${s['min_paid']:.2f}, GMC {sorted(rates)})"}
    return None


def compare(shop: dict, g: dict, inactive_only: list) -> dict:
    missing = sorted(set(shop) - set(g))
    mismatches = []
    for code in sorted(set(shop) & set(g)):
        m = _mismatch(code, shop[code], g[code])
        if m:
            mismatches.append({**m, "shopify": shop[code], "gmc": g[code]})
    return {"missing_in_gmc": missing,
            "of_which_only_inactive_in_gmc": sorted(set(missing) & set(inactive_only)),
            "not_in_shopify": sorted(set(g) - set(shop)), "rate_mismatches": mismatches}


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
    g, inactive_only = ({}, []) if "error" in settings else gmc_countries(settings)
    print(f"  GMC services: {len(settings.get('services', []))}, countries: {len(g)}")
    print("=== Shopify shipping zones ===")
    shop = section("shopify_zones", shopify_countries)
    shop = {} if "error" in shop else shop
    print(f"  Shopify countries: {len(shop)}")
    if shop and g:
        report["comparison"] = compare(shop, g, inactive_only)
        c = report["comparison"]
        print(f"  In Shopify, missing in GMC ({len(c['missing_in_gmc'])}): {c['missing_in_gmc']}")
        print(f"  ...of which only inactive GMC services: {c['of_which_only_inactive_in_gmc']}")
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
