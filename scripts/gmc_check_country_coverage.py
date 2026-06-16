#!/usr/bin/env python3
"""
Check which campaign target countries have no products in GMC.
Identifies the 2 flagged locations causing UNKNOWN campaign status.
"""

import json
import os
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

MERCHANT_ID = "582171114"
SCOPES = ["https://www.googleapis.com/auth/content"]

# 42 campaign target countries
TARGET_COUNTRIES = [
    "US", "GB", "CA", "AU", "NZ", "IE", "DE", "FR", "NL", "BE",
    "AT", "CH", "SE", "NO", "DK", "FI", "PL", "CZ", "RO", "HU",
    "IT", "ES", "PT", "IL", "AE", "SA", "QA", "KW", "ZA", "NG",
    "KE", "JP", "KR", "SG", "HK", "IN", "BR", "MX", "DO", "EC",
    "VN", "KZ"
]

def get_credentials():
    sa_key = os.environ.get("GCP_SA_KEY")
    if not sa_key:
        print("ERROR: GCP_SA_KEY not set")
        sys.exit(1)
    key_data = json.loads(sa_key)
    return service_account.Credentials.from_service_account_info(
        key_data, scopes=SCOPES
    )

def main():
    creds = get_credentials()
    service = build("content", "v2.1", credentials=creds)

    print(f"Checking product coverage for {len(TARGET_COUNTRIES)} campaign countries...")
    print("=" * 60)

    countries_with_products = set()
    countries_no_products = set()

    # Pull all active products and check their targetCountry
    request = service.products().list(merchantId=MERCHANT_ID, maxResults=250)
    
    all_products = []
    while request is not None:
        response = request.execute()
        products = response.get("resources", [])
        all_products.extend(products)
        request = service.products().list_next(request, response)

    print(f"Total products found in GMC: {len(all_products)}")
    print()

    # Map products to their target countries
    country_product_count = {}
    for product in all_products:
        target_country = product.get("targetCountry", "")
        if target_country:
            country_product_count[target_country] = country_product_count.get(target_country, 0) + 1

    print("COVERAGE BY CAMPAIGN COUNTRY:")
    print("-" * 60)
    flagged = []
    for country in TARGET_COUNTRIES:
        count = country_product_count.get(country, 0)
        if count == 0:
            flagged.append(country)
            print(f"  ❌ {country}: 0 products — NO COVERAGE")
        else:
            print(f"  ✅ {country}: {count} products")

    print()
    print("=" * 60)
    print(f"FLAGGED COUNTRIES (0 products): {flagged}")
    print(f"These are the 2 locations causing the UNKNOWN campaign status.")

if __name__ == "__main__":
    main()
