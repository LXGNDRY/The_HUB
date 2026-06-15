"""
fix_gmc_shipping.py
-------------------
Reads current GMC shipping settings, identifies countries in the
56-country ad target list that lack shipping coverage, and patches
the free-shipping service to include all of them.

Merchant ID : 582171114
Target      : All 56 countries targeted in THEE PMax campaign
Rule        : Free shipping, no minimum order value
"""

import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Auth ─────────────────────────────────────────────────────────────────────
SA_KEY_JSON = os.environ.get("GCP_SA_KEY")
if not SA_KEY_JSON:
    sys.exit("ERROR: GCP_SA_KEY not set.")
try:
    sa_info = json.loads(SA_KEY_JSON)
except json.JSONDecodeError as e:
    sys.exit(f"ERROR: GCP_SA_KEY is not valid JSON: {e}")

creds = service_account.Credentials.from_service_account_info(
    sa_info,
    scopes=["https://www.googleapis.com/auth/content"],
)
service = build("content", "v2.1", credentials=creds)

MERCHANT_ID = 582171114

# ── All 56 targeted countries ─────────────────────────────────────────────────
TARGET_COUNTRIES = [
    # Tier 1
    "US", "GB", "CA", "FR", "DE", "IE", "ES", "IT", "AU", "NZ",
    "JP", "KR", "SG", "HK", "NL", "BE", "CH", "NO", "SE", "DK",
    "FI", "AT", "PT", "GR", "CZ", "PL", "HU", "RO", "AE", "QA",
    "KW", "BH", "SA", "IL", "MX",
    # Tier 2
    "AR", "CL", "CO", "EC", "PE", "DO", "SV", "GT", "JM", "PA",
    "PR", "TT", "KZ", "AM", "GE", "MA", "EG", "JO", "LB", "ZA",
    "MY",
]

def get_shipping_settings():
    resp = service.shippingsettings().get(
        merchantId=MERCHANT_ID,
        accountId=MERCHANT_ID,
    ).execute()
    return resp

def get_covered_countries(settings):
    """Return set of country codes already covered by any shipping service."""
    covered = set()
    for svc in settings.get("services", []):
        for country in svc.get("deliveryCountries", []):
            covered.add(country)
    return covered

def find_free_shipping_service(settings):
    """Find the existing free shipping service to patch."""
    for i, svc in enumerate(settings.get("services", [])):
        name = svc.get("name", "").lower()
        # Look for free shipping service (no rate table / flatRate of 0)
        rate_groups = svc.get("rateGroups", [])
        is_free = False
        if not rate_groups:
            is_free = True
        else:
            for rg in rate_groups:
                single_value = rg.get("singleValue", {})
                if single_value.get("flatRate", {}).get("value") == "0":
                    is_free = True
        if is_free or "free" in name:
            return i, svc
    return None, None

def main():
    print(f"Fetching shipping settings for merchant {MERCHANT_ID}...")
    settings = get_shipping_settings()

    services = settings.get("services", [])
    print(f"Found {len(services)} shipping service(s):")
    for svc in services:
        countries = svc.get("deliveryCountries", [])
        print(f"  '{svc.get('name')}' — {len(countries)} countries: {sorted(countries)}")

    covered = get_covered_countries(settings)
    print(f"\nCurrently covered: {len(covered)} countries")

    missing = [c for c in TARGET_COUNTRIES if c not in covered]
    print(f"Missing from 56-country target list: {len(missing)} — {sorted(missing)}")

    if not missing:
        print("\nAll 56 target countries already have shipping coverage. Nothing to do.")
        return

    # Find the free shipping service to patch
    idx, free_svc = find_free_shipping_service(settings)
    if free_svc is None:
        print("\nNo free shipping service found. Looking for any active service to extend...")
        # Fall back: use first active service
        for i, svc in enumerate(services):
            if svc.get("active", False):
                idx, free_svc = i, svc
                break

    if free_svc is None:
        sys.exit("ERROR: No active shipping service found to patch. Please check GMC manually.")

    print(f"\nPatching service: '{free_svc.get('name')}' (index {idx})")

    # Add missing countries to this service
    existing_countries = free_svc.get("deliveryCountries", [])
    updated_countries = sorted(set(existing_countries) | set(missing))
    settings["services"][idx]["deliveryCountries"] = updated_countries

    print(f"Updated deliveryCountries ({len(updated_countries)}): {updated_countries}")

    # Push the update
    print("\nPushing updated shipping settings to GMC...")
    result = service.shippingsettings().update(
        merchantId=MERCHANT_ID,
        accountId=MERCHANT_ID,
        body=settings,
    ).execute()

    # Verify
    updated_settings = get_shipping_settings()
    updated_covered = get_covered_countries(updated_settings)
    still_missing = [c for c in TARGET_COUNTRIES if c not in updated_covered]

    print(f"\n=== RESULT ===")
    print(f"Countries now covered: {len(updated_covered)}")
    print(f"Still missing: {len(still_missing)} — {still_missing}")
    if not still_missing:
        print("SUCCESS: All 56 target countries now have shipping coverage.")
    else:
        print(f"WARNING: {len(still_missing)} countries still missing coverage: {still_missing}")

if __name__ == "__main__":
    main()
