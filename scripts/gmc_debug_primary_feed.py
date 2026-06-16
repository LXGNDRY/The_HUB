#!/usr/bin/env python3
"""
Debug why CA, PL, DO are missing from GMC primary feed.
Checks: datafeeds list, datafeed statuses, and searches for products
with those target countries across all data sources.
"""

import json, os, sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

MERCHANT_ID = "582171114"
SCOPES = ["https://www.googleapis.com/auth/content"]
MISSING = ["CA", "PL", "DO"]

def get_service():
    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GCP_SA_KEY"]), scopes=SCOPES
    )
    return build("content", "v2.1", credentials=creds)

def main():
    svc = get_service()

    # 1. List all datafeeds and their targets
    print("=" * 60)
    print("ALL GMC DATA SOURCES (datafeeds)")
    print("=" * 60)
    try:
        resp = svc.datafeeds().list(merchantId=MERCHANT_ID).execute()
        feeds = resp.get("resources", [])
        print(f"Total datafeeds: {len(feeds)}")
        for f in feeds:
            targets = f.get("targets", [])
            countries = [t.get("country","") for t in targets]
            print(f"\n  ID: {f.get('id')} | Name: {f.get('name')}")
            print(f"  Fetch URL: {f.get('fetchSchedule',{}).get('fetchUrl','N/A')}")
            print(f"  Content type: {f.get('contentType','?')}")
            print(f"  Target countries: {countries}")
            print(f"  Included destinations: {[t.get('includedDestinations',[]) for t in targets]}")
    except Exception as e:
        print(f"  Datafeeds error: {e}")

    # 2. Check datafeed statuses for CA, PL, DO
    print()
    print("=" * 60)
    print("DATAFEED STATUSES")
    print("=" * 60)
    try:
        resp = svc.datafeeds().list(merchantId=MERCHANT_ID).execute()
        feeds = resp.get("resources", [])
        for f in feeds:
            fid = f.get("id")
            try:
                status = svc.datafeedstatuses().get(
                    merchantId=MERCHANT_ID, datafeedId=fid
                ).execute()
                errors = status.get("itemsTotal", 0)
                valid = status.get("itemsValid", 0)
                print(f"\n  Feed {fid} ({f.get('name')}):")
                print(f"  Total items: {errors} | Valid: {valid}")
                # Check country-level status
                country_statuses = status.get("country", [])
                for cs in country_statuses:
                    c = cs.get("country","")
                    if c in MISSING:
                        print(f"  ⚠️  {c}: {cs}")
            except Exception as e:
                print(f"  Feed {fid} status error: {e}")
    except Exception as e:
        print(f"  Status check error: {e}")

    # 3. Search specifically for products targeting CA, PL, DO
    print()
    print("=" * 60)
    print("SEARCHING FOR CA/PL/DO PRODUCTS ACROSS ALL PAGES")
    print("=" * 60)
    country_counts = {"CA": 0, "PL": 0, "DO": 0}
    try:
        page_token = None
        page = 0
        while True:
            page += 1
            kwargs = {"merchantId": MERCHANT_ID, "maxResults": 250}
            if page_token:
                kwargs["pageToken"] = page_token
            resp = svc.products().list(**kwargs).execute()
            products = resp.get("resources", [])
            if not products:
                break
            for p in products:
                tc = p.get("targetCountry", "")
                if tc in country_counts:
                    country_counts[tc] += 1
            page_token = resp.get("nextPageToken")
            print(f"  Page {page}: {len(products)} products | Running totals: {country_counts}")
            if not page_token:
                break
    except Exception as e:
        print(f"  Product search error: {e}")

    print()
    print("FINAL COUNTS:")
    for c, count in country_counts.items():
        status = "✅" if count > 0 else "❌"
        print(f"  {status} {c}: {count} products")

if __name__ == "__main__":
    main()
