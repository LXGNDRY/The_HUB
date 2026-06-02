#!/usr/bin/env python3
"""
gmc_link_supplemental.py — Legendary Branding
Links supplemental source (ID: 10655362673) to the primary Shopify feed
by patching it with feedLabel + contentLanguage via Merchant API v1beta.

Supplemental Source ID : 10655362673
Merchant ID            : 582171114
"""
import os, json, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

SA_KEY_JSON           = os.environ["GCP_SA_KEY"]
MERCHANT_ID           = "582171114"
SUPPLEMENTAL_ID       = "10655362673"

# ── Auth ──────────────────────────────────────────────────────────────────────
creds = service_account.Credentials.from_service_account_info(
    json.loads(SA_KEY_JSON),
    scopes=["https://www.googleapis.com/auth/content"],
)
creds.refresh(GoogleRequest())
token = creds.token

HEADERS = {
    "Authorization": f"Bearer {token}",
    "Content-Type":  "application/json",
}

BASE_V1BETA = f"https://merchantapi.googleapis.com/datasources/v1beta/accounts/{MERCHANT_ID}/dataSources"
BASE_V21    = f"https://shoppingcontent.googleapis.com/content/v2.1/{MERCHANT_ID}"

# ── Step 1: List data sources to identify primary feed ───────────────────────
print("=" * 70)
print("STEP 1: Listing GMC data sources (Merchant API v1beta)")
print("=" * 70)

resp = requests.get(
    BASE_V1BETA,
    headers=HEADERS,
    params={"pageSize": 50},
)
print(f"  Status: {resp.status_code}")

if resp.status_code != 200:
    print(f"  v1beta list failed: {resp.text}")
    print()
    print("  Falling back to Content API v2.1 datasources...")
    # Try Content API v2.1 datafeeds endpoint instead
    feeds_resp = requests.get(
        f"{BASE_V21}/datafeeds",
        headers=HEADERS,
    )
    print(f"  Content API status: {feeds_resp.status_code}")
    print(f"  Response: {feeds_resp.text[:2000]}")
else:
    sources = resp.json().get("dataSources", [])
    print(f"  Sources found: {len(sources)}")
    primary_name = None
    for s in sources:
        name      = s.get("name", "")
        disp_name = s.get("displayName", "")
        source_id = name.split("/")[-1] if "/" in name else ""
        kind      = "PRIMARY" if "primaryProductDataSource" in s else \
                    "SUPPLEMENTAL" if "supplementalProductDataSource" in s else "OTHER"
        print(f"  [{kind}] '{disp_name}' | ID: {source_id}")
        if kind == "PRIMARY" and primary_name is None:
            primary_name = name
            primary_id   = source_id

# ── Step 2: Patch supplemental source — set feedLabel to match primary ────────
print()
print("=" * 70)
print("STEP 2: Patching supplemental source feedLabel")
print("=" * 70)

# In Merchant API v1beta, supplemental sources are linked to primary sources
# by matching on feedLabel + contentLanguage. Setting these on the supplemental
# source causes GMC to apply it to all primary sources with the same feedLabel.
patch_url  = f"{BASE_V1BETA}/{SUPPLEMENTAL_ID}"
patch_body = {
    "name":        f"accounts/{MERCHANT_ID}/dataSources/{SUPPLEMENTAL_ID}",
    "displayName": "Title Overrides — Supplemental Feed",
    "supplementalProductDataSource": {
        "feedLabel":         "US",
        "contentLanguage":   "en",
    },
}

patch_resp = requests.patch(
    patch_url,
    headers=HEADERS,
    params={"updateMask": "displayName,supplementalProductDataSource"},
    json=patch_body,
)

print(f"  PATCH status : {patch_resp.status_code}")
print(f"  Response     : {json.dumps(patch_resp.json(), indent=2)}")

if patch_resp.status_code in (200, 204):
    print()
    print("=" * 70)
    print("SUCCESS — Supplemental feed linked")
    print("=" * 70)
    print(f"  Source ID    : {SUPPLEMENTAL_ID}")
    print(f"  Feed label   : US")
    print(f"  Language     : en")
    print()
    print("  GMC will now apply title overrides from this supplemental")
    print("  source to all matching primary feed products.")
    print("  'Used in' column will update in GMC UI within a few hours.")
    print("  Title changes propagate to Shopping ads within 24-48 hours.")
else:
    print()
    print("  PATCH failed — see response above for details.")
    print("  Manual fallback: In GMC > Data sources > Supplemental sources")
    print("  > click 'Perplexed' > edit and set Feed label to 'US'.")
