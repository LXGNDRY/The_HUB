"""
fix_gmc_shipping.py
-------------------
Adds free-shipping service entries for the 5 countries missing from GMC:
  AM (Armenia), JM (Jamaica), PR (Puerto Rico), QA (Qatar), TT (Trinidad & Tobago)

Each country needs its own service entry with:
  - deliveryCountry: ISO code
  - currency: local currency
  - singleValue flatRate of 0
  - deliveryTime: 6-12 transit + 2 handling (matching existing intl services)

Merchant ID: 582171114
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

# ── Countries to add (code → local currency) ─────────────────────────────────
MISSING_COUNTRIES = {
    "AM": "AMD",   # Armenia
    "JM": "JMD",   # Jamaica
    "PR": "USD",   # Puerto Rico (uses USD)
    "QA": "QAR",   # Qatar
    "TT": "TTD",   # Trinidad & Tobago
}

def build_free_service(country_code, currency):
    """Build a free-shipping service entry matching the existing intl pattern."""
    return {
        "name": f"free_shipping_{country_code}",
        "active": True,
        "deliveryCountry": country_code,
        "currency": currency,
        "deliveryTime": {
            "minTransitTimeInDays": 6,
            "maxTransitTimeInDays": 12,
            "minHandlingTimeInDays": 2,
            "maxHandlingTimeInDays": 2,
        },
        "shipmentType": "delivery",
        "rateGroups": [
            {
                "singleValue": {
                    "flatRate": {
                        "value": "0",
                        "currency": currency,
                    }
                }
            }
        ],
    }

def main():
    print(f"Fetching shipping settings for merchant {MERCHANT_ID}...")
    settings = service.shippingsettings().get(
        merchantId=MERCHANT_ID, accountId=MERCHANT_ID
    ).execute()

    existing_services = settings.get("services", [])
    existing_countries = {svc.get("deliveryCountry") for svc in existing_services}
    print(f"Existing services: {len(existing_services)} covering {len(existing_countries)} countries")

    # Determine which are still missing
    to_add = {k: v for k, v in MISSING_COUNTRIES.items() if k not in existing_countries}
    already_present = {k: v for k, v in MISSING_COUNTRIES.items() if k in existing_countries}

    if already_present:
        print(f"Already present (skip): {list(already_present.keys())}")

    if not to_add:
        print("Nothing to add — all target countries already have shipping entries.")
        return

    print(f"\nAdding {len(to_add)} new free-shipping services: {list(to_add.keys())}")

    # Append new service entries
    new_services = [build_free_service(code, currency) for code, currency in to_add.items()]
    settings["services"] = existing_services + new_services

    print("Pushing updated shipping settings to GMC...")
    service.shippingsettings().update(
        merchantId=MERCHANT_ID,
        accountId=MERCHANT_ID,
        body=settings,
    ).execute()
    print("Push complete.")

    # Verify
    updated = service.shippingsettings().get(
        merchantId=MERCHANT_ID, accountId=MERCHANT_ID
    ).execute()
    updated_countries = {svc.get("deliveryCountry") for svc in updated.get("services", [])}

    still_missing = [c for c in MISSING_COUNTRIES if c not in updated_countries]
    confirmed = [c for c in MISSING_COUNTRIES if c in updated_countries]

    print(f"\n=== RESULT ===")
    print(f"Confirmed added: {confirmed}")
    print(f"Still missing:   {still_missing}")

    if not still_missing:
        print("\nSUCCESS: All 5 countries now have free-shipping coverage in GMC.")
    else:
        sys.exit(f"ERROR: {len(still_missing)} countries still missing: {still_missing}")

if __name__ == "__main__":
    main()
