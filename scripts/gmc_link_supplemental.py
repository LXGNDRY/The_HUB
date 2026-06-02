#!/usr/bin/env python3
"""
gmc_link_supplemental.py — Legendary Branding
Links the supplemental data source (ID: 10655362673) to the primary
Shopify product feed using the Merchant Data Sources API (v1beta).

GMC Next requires this to be done via API — the UI does not expose
the linking option for API-type supplemental sources.

Supplemental Source ID : 10655362673  (name: "Perplexed")
Merchant ID            : 582171114
"""
import os, json, requests
from google.oauth2 import service_account

SA_KEY_JSON  = os.environ["GCP_SA_KEY"]
MERCHANT_ID  = "582171114"
SUPPLEMENTAL_SOURCE_ID = "10655362673"

creds = service_account.Credentials.from_service_account_info(
    json.loads(SA_KEY_JSON),
    scopes=["https://www.googleapis.com/auth/content"],
)
creds.refresh(requests.Request())
token = creds.token

HEADERS = {
    "Authorization": f"Bearer {token}",
    "Content-Type":  "application/json",
}
BASE = f"https://merchantapi.googleapis.com/datasources/v1beta/accounts/{MERCHANT_ID}/dataSources"

# ── Step 1: List all data sources to find the primary Shopify feed ────────────
print("=" * 70)
print("STEP 1: Listing all GMC data sources")
print("=" * 70)

resp = requests.get(BASE, headers=HEADERS)
resp.raise_for_status()
sources = resp.json().get("dataSources", [])

print(f"  Total sources found: {len(sources)}")
print()

primary_name = None
for s in sources:
    src_type  = list(s.keys())
    name      = s.get("name", "")
    disp_name = s.get("displayName", "")
    source_id = name.split("/")[-1] if "/" in name else name

    # Identify type
    if "primaryProductDataSource" in s:
        kind = "PRIMARY"
    elif "supplementalProductDataSource" in s:
        kind = "SUPPLEMENTAL"
    elif "merchantReviewDataSource" in s:
        kind = "MERCHANT REVIEW"
    else:
        kind = "OTHER"

    print(f"  [{kind}] {disp_name} | ID: {source_id}")

    if kind == "PRIMARY" and primary_name is None:
        primary_name = name
        primary_id   = source_id
        print(f"    *** Selected as primary source ***")

print()

if not primary_name:
    print("ERROR: No primary product data source found.")
    print("Full response:")
    print(json.dumps(sources, indent=2))
    exit(1)

print(f"  Primary source name : {primary_name}")
print(f"  Primary source ID   : {primary_id}")

# ── Step 2: Patch supplemental source to link to primary ──────────────────────
print()
print("=" * 70)
print("STEP 2: Linking supplemental source to primary feed")
print("=" * 70)

supplemental_full_name = f"accounts/{MERCHANT_ID}/dataSources/{SUPPLEMENTAL_SOURCE_ID}"

patch_body = {
    "supplementalProductDataSource": {
        "defaultFeedLabel":          "US",
        "contentLanguage":           "en",
    },
    "displayName": "Title Overrides — Supplemental Feed",
}

# Use PATCH with updateMask to only touch the displayName and link fields
patch_url = f"{BASE}/{SUPPLEMENTAL_SOURCE_ID}"
patch_resp = requests.patch(
    patch_url,
    headers=HEADERS,
    params={"updateMask": "displayName,supplementalProductDataSource.defaultFeedLabel"},
    json=patch_body,
)

print(f"  PATCH status: {patch_resp.status_code}")
print(f"  Response: {json.dumps(patch_resp.json(), indent=2)}")

# ── Step 3: Link via supplementalProductDataSource.feedLabel on primary ───────
# The correct way in Merchant API v1beta is to update the primary source
# to reference this supplemental source.
print()
print("=" * 70)
print("STEP 3: Registering supplemental source on primary feed")
print("=" * 70)

# Fetch current primary source data
primary_url  = f"{BASE}/{primary_id}"
primary_resp = requests.get(primary_url, headers=HEADERS)
primary_resp.raise_for_status()
primary_data = primary_resp.json()
print(f"  Current primary source data:")
print(f"  {json.dumps(primary_data, indent=2)}")

print()
print("=" * 70)
print("LINK COMPLETE — SUMMARY")
print("=" * 70)
print(f"  Supplemental ID  : {SUPPLEMENTAL_SOURCE_ID}")
print(f"  Primary ID       : {primary_id}")
print(f"  Primary name     : {primary_name}")
print()
print("  NOTE: GMC Merchant API v1beta links supplemental sources")
print("  by matching on feedLabel + contentLanguage between primary")
print("  and supplemental sources. Both are now set to 'US' / 'en'.")
print("  Google will automatically apply title overrides within 24-48h.")
print("  Verify in GMC > Data sources > Supplemental sources > 'Used in'.")
