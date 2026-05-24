#!/usr/bin/env python3
"""
gmc_ads_link.py — Legendary Branding
Check and create the Merchant Center <-> Google Ads account link.

GMC Merchant ID:      582171114
Google Ads Customer:  1137623123

Uses Content API v2.1 accountstatuses + liasettings + accountlinks.
The link is created by inserting a link request from GMC side,
which auto-approves when the same Google account owns both.
"""
import os, json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SA_KEY_JSON = os.environ["GCP_SA_KEY"]
MERCHANT_ID = "582171114"
ADS_CUSTOMER_ID = "1137623123"

creds = service_account.Credentials.from_service_account_info(
    json.loads(SA_KEY_JSON),
    scopes=["https://www.googleapis.com/auth/content"],
)
service = build("content", "v2.1", credentials=creds)

print("=" * 60)
print("GMC <-> Google Ads Link Check")
print("=" * 60)
print(f"  Merchant ID:      {MERCHANT_ID}")
print(f"  Google Ads ID:    {ADS_CUSTOMER_ID}")

# ── Step 1: Check existing links ─────────────────────────────
print("\nSTEP 1: Checking existing Google Ads links...")
try:
    result = service.accounts().get(
        merchantId=MERCHANT_ID,
        accountId=MERCHANT_ID
    ).execute()
    
    # Check googleAdsLinks in account
    ads_links = result.get("googleAdsLinks", [])
    print(f"  Existing Google Ads links: {len(ads_links)}")
    
    already_linked = False
    for link in ads_links:
        linked_id = link.get("googleAdsId", "")
        status = link.get("status", "unknown")
        print(f"    - Ads ID: {linked_id} | Status: {status}")
        if linked_id == ADS_CUSTOMER_ID:
            already_linked = True
            print(f"  ✅ Already linked to {ADS_CUSTOMER_ID} with status: {status}")

    if already_linked:
        print("\n✅ LINK ALREADY EXISTS — no action needed.")
        print("  Google Shopping ads can use Merchant Center 582171114")
        exit(0)
        
except HttpError as e:
    print(f"  Account GET error: {e}")

# ── Step 2: Create the link ───────────────────────────────────
print(f"\nSTEP 2: Creating link from GMC {MERCHANT_ID} -> Ads {ADS_CUSTOMER_ID}...")
try:
    link_body = {
        "googleAdsId": ADS_CUSTOMER_ID
    }
    result = service.accounts().link(
        merchantId=MERCHANT_ID,
        accountId=MERCHANT_ID,
        body={"googleAdsLinks": [{"googleAdsId": ADS_CUSTOMER_ID}]}
    ).execute()
    print(f"  Link request result: {json.dumps(result, indent=2)[:300]}")
except HttpError as e:
    print(f"  Link via accounts.link failed: {e}")
    # Try alternative: accounts.update with googleAdsLinks
    print("\nSTEP 2b: Trying accounts.update with googleAdsLinks...")
    try:
        # First get current account to build update payload
        acct = service.accounts().get(
            merchantId=MERCHANT_ID,
            accountId=MERCHANT_ID
        ).execute()
        
        existing_links = acct.get("googleAdsLinks", [])
        # Add new link if not present
        new_link = {"googleAdsId": ADS_CUSTOMER_ID, "status": "active"}
        existing_links.append(new_link)
        acct["googleAdsLinks"] = existing_links
        
        updated = service.accounts().update(
            merchantId=MERCHANT_ID,
            accountId=MERCHANT_ID,
            body=acct
        ).execute()
        
        new_links = updated.get("googleAdsLinks", [])
        print(f"  Updated account. Google Ads links: {len(new_links)}")
        for link in new_links:
            print(f"    - Ads ID: {link.get('googleAdsId')} | Status: {link.get('status')}")
            
    except HttpError as e2:
        print(f"  accounts.update also failed: {e2}")
        print("\n  ⚠️  The Content API service account cannot create this link.")
        print("  This link must be created in Google Ads UI:")
        print("  Google Ads → Tools & Settings → Linked accounts → Google Merchant Center")
        print(f"  Link Merchant Center ID: {MERCHANT_ID}")

print("\n" + "=" * 60)
print("COMPLETE")
print("=" * 60)
