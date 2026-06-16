#!/usr/bin/env python3
"""
Check GMC data sources and which countries have active product data.
Cross-references against the original 42 campaign target countries.
"""

import json
import os
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

MERCHANT_ID = "582171114"
SCOPES = ["https://www.googleapis.com/auth/content"]

CAMPAIGN_42 = [
    "US", "GB", "CA", "AU", "NZ", "IE", "DE", "FR", "NL", "BE",
    "AT", "CH", "SE", "NO", "DK", "FI", "PL", "CZ", "RO", "HU",
    "IT", "ES", "PT", "IL", "AE", "SA", "QA", "KW", "ZA", "NG",
    "KE", "JP", "KR", "SG", "HK", "IN", "BR", "MX", "DO", "EC",
    "VN", "KZ"
]

def get_service():
    sa_key = os.environ.get("GCP_SA_KEY")
    if not sa_key:
        print("ERROR: GCP_SA_KEY not set")
        sys.exit(1)
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_key), scopes=SCOPES
    )
    return build("content", "v2.1", credentials=creds)

def main():
    service = get_service()

    # 1. List all data sources
    print("=" * 60)
    print("GMC DATA SOURCES")
    print("=" * 60)
    try:
        ds_resp = service.datafeeds().list(merchantId=MERCHANT_ID).execute()
        feeds = ds_resp.get("resources", [])
        print(f"Total data sources: {len(feeds)}")
        for feed in feeds:
            targets = feed.get("targets", [])
            countries = [t.get("country", "") for t in targets]
            print(f"  Feed: {feed.get('name','?')} (ID: {feed.get('id','?')})")
            print(f"    Format: {feed.get('format', {}).get('fileEncoding','?')}")
            print(f"    Target countries: {countries}")
    except Exception as e:
        print(f"  Datafeeds list error: {e}")

    # 2. Check product counts by country using statuses
    print()
    print("=" * 60)
    print("PRODUCT COUNTS BY COUNTRY (from productstatuses)")
    print("=" * 60)
    
    country_counts = {}
    try:
        # Sample first 250 products and check target countries
        resp = service.products().list(
            merchantId=MERCHANT_ID,
            maxResults=250
        ).execute()
        
        products = resp.get("resources", [])
        print(f"Sample size: {len(products)} products")
        
        for p in products:
            tc = p.get("targetCountry", "")
            if tc:
                country_counts[tc] = country_counts.get(tc, 0) + 1
                
    except Exception as e:
        print(f"  Products list error: {e}")

    print()
    print("CAMPAIGN 42 vs DATA SOURCES:")
    print("-" * 40)
    missing = []
    for c in CAMPAIGN_42:
        count = country_counts.get(c, 0)
        if count == 0:
            missing.append(c)
            print(f"  ❌ {c}: NO PRODUCTS FOUND")
        else:
            print(f"  ✅ {c}: {count} products")
    
    print()
    print(f"MISSING COUNTRIES: {missing}")

if __name__ == "__main__":
    main()
