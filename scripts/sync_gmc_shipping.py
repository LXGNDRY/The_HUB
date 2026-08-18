"""
sync_gmc_shipping.py
--------------------
1. Reads ALL Shopify shipping zones + rates (free vs paid, per country)
2. Reads current GMC shipping settings
3. Builds a diff — countries in Shopify but missing/wrong in GMC
4. Pushes corrected services to GMC so they match Shopify exactly

Auth:
  SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET  → Shopify REST API
  GCP_SA_KEY                                 → GMC Content API v2.1

Merchant ID : 582171114
Shop        : lngndny.myshopify.com
"""

import json
import os
import sys
import requests

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Config ────────────────────────────────────────────────────────────────────
SHOP            = "lngndny.myshopify.com"
MERCHANT_ID     = 582171114
API_VERSION     = "2026-04"

# ── Shopify Auth ──────────────────────────────────────────────────────────────
SHOPIFY_ADMIN_TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN")
CLIENT_ID     = os.environ.get("SHOPIFY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET")

if CLIENT_ID and CLIENT_SECRET:
    token_resp = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        json={"grant_type": "client_credentials",
              "client_id": CLIENT_ID,
              "client_secret": CLIENT_SECRET},
    )
    if token_resp.status_code != 200:
        sys.exit(f"ERROR: Shopify token exchange failed: {token_resp.text}")
    SHOPIFY_TOKEN = token_resp.json()["access_token"]
elif SHOPIFY_ADMIN_TOKEN:
    SHOPIFY_TOKEN = SHOPIFY_ADMIN_TOKEN
else:
    sys.exit("ERROR: Set SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET, or SHOPIFY_ADMIN_TOKEN.")
SHOPIFY_HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN}

# ── GMC Auth ──────────────────────────────────────────────────────────────────
SA_KEY_JSON = os.environ.get("GCP_SA_KEY")
if not SA_KEY_JSON:
    sys.exit("ERROR: GCP_SA_KEY not set.")
sa_info = json.loads(SA_KEY_JSON)
creds = service_account.Credentials.from_service_account_info(
    sa_info, scopes=["https://www.googleapis.com/auth/content"])
gmc = build("content", "v2.1", credentials=creds)

# ── ISO country code → local currency map ────────────────────────────────────
# Used when GMC needs a currency for a country not yet in its services
CURRENCY_MAP = {
    "US": "USD", "GB": "GBP", "CA": "CAD", "AU": "AUD", "NZ": "NZD",
    "JP": "JPY", "KR": "KRW", "SG": "SGD", "HK": "HKD", "CH": "CHF",
    "NO": "NOK", "SE": "SEK", "DK": "DKK", "CZ": "CZK", "PL": "PLN",
    "HU": "HUF", "RO": "RON", "IL": "ILS", "MX": "MXN", "AR": "ARS",
    "CL": "CLP", "CO": "COP", "EC": "USD", "PE": "PEN", "DO": "DOP",
    "SV": "USD", "GT": "GTQ", "JM": "JMD", "PA": "USD", "PR": "USD",
    "TT": "TTD", "KZ": "KZT", "AM": "AMD", "GE": "GEL", "MA": "MAD",
    "EG": "EGP", "JO": "JOD", "LB": "LBP", "ZA": "ZAR", "MY": "MYR",
    "AE": "AED", "QA": "QAR", "KW": "KWD", "BH": "BHD", "SA": "SAR",
    # EU
    "FR": "EUR", "DE": "EUR", "IE": "EUR", "ES": "EUR", "IT": "EUR",
    "NL": "EUR", "BE": "EUR", "PT": "EUR", "GR": "EUR", "AT": "EUR",
    "FI": "EUR", "SK": "EUR",
}

def get_shopify_zones():
    """Return dict: country_code → {free: bool, express_price: str|None}"""
    r = requests.get(
        f"https://{SHOP}/admin/api/{API_VERSION}/shipping_zones.json",
        headers=SHOPIFY_HEADERS,
    )
    r.raise_for_status()
    zones = r.json().get("shipping_zones", [])

    country_rates = {}  # code → {free: bool, express_usd: str|None, zone_name: str}

    for zone in zones:
        zone_name = zone.get("name", "")
        countries = zone.get("countries", [])
        price_rates = zone.get("price_based_shipping_rates", [])
        weight_rates = zone.get("weight_based_shipping_rates", [])
        all_rates = price_rates + weight_rates

        has_free = any(float(r.get("price", "999")) == 0 for r in all_rates)
        express = next(
            (r for r in all_rates if float(r.get("price", "0")) > 0),
            None,
        )
        express_price = str(float(express["price"])) if express else None

        for country in countries:
            code = country.get("code", "")
            if code:
                country_rates[code] = {
                    "free": has_free,
                    "express_price": express_price,
                    "zone_name": zone_name,
                    "currency": country.get("currency", "USD"),
                }

    return country_rates

def get_gmc_settings():
    return gmc.shippingsettings().get(
        merchantId=MERCHANT_ID, accountId=MERCHANT_ID
    ).execute()

def get_gmc_coverage(settings):
    """Return dict: country_code → list of service names covering it."""
    coverage = {}
    for svc in settings.get("services", []):
        code = svc.get("deliveryCountry", "")
        rate_val = svc.get("rateGroups", [{}])[0].get("singleValue", {}).get("flatRate", {}).get("value", "?")
        svc_type = "free" if rate_val == "0" else f"paid_{rate_val}"
        coverage.setdefault(code, []).append(svc_type)
    return coverage

def build_service(country_code, is_free, price_usd, currency, transit_min, transit_max):
    label = "free shipping" if is_free else f"express shipping"
    price_str = "0" if is_free else str(price_usd)
    return {
        "name": f"{'free' if is_free else 'express'}_{country_code}_sync",
        "active": True,
        "deliveryCountry": country_code,
        "currency": currency,
        "deliveryTime": {
            "minTransitTimeInDays": transit_min,
            "maxTransitTimeInDays": transit_max,
            "minHandlingTimeInDays": 2,
            "maxHandlingTimeInDays": 2,
        },
        "shipmentType": "delivery",
        "rateGroups": [{
            "singleValue": {
                "flatRate": {"value": price_str, "currency": currency}
            }
        }],
    }

def main():
    print("=" * 60)
    print("Step 1 — Fetching Shopify shipping zones...")
    shopify_rates = get_shopify_zones()
    print(f"  {len(shopify_rates)} countries configured in Shopify")

    print("\nStep 2 — Fetching GMC shipping settings...")
    gmc_settings = get_gmc_settings()
    gmc_coverage = get_gmc_coverage(gmc_settings)
    print(f"  {len(gmc_coverage)} countries in GMC")

    print("\nStep 3 — Comparing...")
    to_add    = []
    conflicts = []
    matched   = []

    for code, shopify in shopify_rates.items():
        currency = shopify.get("currency") or CURRENCY_MAP.get(code, "USD")
        gmc_svcs = gmc_coverage.get(code, [])

        if not gmc_svcs:
            # Completely missing from GMC — add it
            to_add.append((code, shopify, currency))
        else:
            # Check if free/paid status matches
            gmc_has_free = any(s == "free" for s in gmc_svcs)
            if shopify["free"] and not gmc_has_free:
                conflicts.append((code, "Shopify=FREE but GMC=paid only", shopify, currency))
            else:
                matched.append(code)

    print(f"  Matched correctly: {len(matched)}")
    print(f"  Missing from GMC:  {len(to_add)} — {[c for c,_,__ in to_add]}")
    print(f"  Conflicts:         {len(conflicts)} — {[c for c,_,__,___ in conflicts]}")

    if not to_add and not conflicts:
        print("\nAll Shopify shipping rates already match GMC. Nothing to update.")
        return

    new_services = list(gmc_settings.get("services", []))

    # Add missing countries
    for code, shopify, currency in to_add:
        transit_min = 3 if shopify["zone_name"].lower() in ("domestic","united states") else 6
        transit_max = 4 if transit_min == 3 else 12
        if shopify["free"]:
            new_services.append(build_service(code, True, "0", currency, transit_min, transit_max))
            print(f"  + Adding FREE  {code} ({currency})")
        if shopify["express_price"]:
            new_services.append(build_service(code, False, shopify["express_price"], currency, transit_min, transit_max))
            print(f"  + Adding EXPRESS {code} @ {shopify['express_price']} {currency}")

    # Fix conflicts (add missing free service, keep existing paid)
    for code, reason, shopify, currency in conflicts:
        transit_min = 3 if shopify["zone_name"].lower() in ("domestic","united states") else 6
        transit_max = 4 if transit_min == 3 else 12
        new_services.append(build_service(code, True, "0", currency, transit_min, transit_max))
        print(f"  ~ Fixing {code}: {reason} — adding FREE service")

    gmc_settings["services"] = new_services

    print(f"\nStep 4 — Pushing {len(new_services)} total services to GMC...")
    gmc.shippingsettings().update(
        merchantId=MERCHANT_ID,
        accountId=MERCHANT_ID,
        body=gmc_settings,
    ).execute()
    print("  Push complete.")

    # Verify
    print("\nStep 5 — Verifying...")
    updated_settings = get_gmc_settings()
    updated_coverage = get_gmc_coverage(updated_settings)

    still_missing = [c for c in shopify_rates if c not in updated_coverage]
    print(f"  GMC now covers: {len(updated_coverage)} countries")
    print(f"  Still missing after push: {still_missing}")

    # Final comparison
    print("\n=== FINAL DIFF (Shopify vs GMC) ===")
    all_codes = sorted(set(list(shopify_rates.keys()) + list(updated_coverage.keys())))
    mismatches = 0
    for code in all_codes:
        in_shopify = code in shopify_rates
        in_gmc = code in updated_coverage
        if in_shopify and not in_gmc:
            print(f"  MISSING IN GMC : {code}")
            mismatches += 1
        elif not in_shopify and in_gmc:
            pass  # GMC has extra coverage — fine, don't flag
    
    if mismatches == 0:
        print("  SUCCESS: All Shopify-configured countries are covered in GMC.")
    else:
        print(f"  WARNING: {mismatches} Shopify countries still not in GMC.")

    # Save diff report
    os.makedirs("outputs", exist_ok=True)
    report = {
        "shopify_countries": len(shopify_rates),
        "gmc_countries_after": len(updated_coverage),
        "added": [c for c, _, __ in to_add],
        "conflicts_fixed": [c for c, _, __, ___ in conflicts],
        "still_missing": still_missing,
    }
    with open("outputs/shipping_sync_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to outputs/shipping_sync_report.json")

if __name__ == "__main__":
    main()
