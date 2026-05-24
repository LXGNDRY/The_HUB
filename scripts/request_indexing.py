#!/usr/bin/env python3
"""
request_indexing.py
Uses the Google Search Console URL Inspection API to request indexing
for URLs that are not yet indexed.

Auth: GCP service account (GCP_SA_KEY) — no token rotation needed.
Prerequisite: g-indexnow@idx-lngndny.iam.gserviceaccount.com must be
added as a user in Search Console → Settings → Users and permissions
for sc-domain:legendary-branding.com
"""
import os, json, sys, time
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

SITE_URL = "sc-domain:legendary-branding.com"
SCOPES   = ["https://www.googleapis.com/auth/webmasters"]

URLS_TO_INDEX = [
    "https://legendary-branding.com/products/mountain-trek-unisex-boxy-t-shirt",
    "https://legendary-branding.com/products/summer-vibes-cropped-boxy-tank-top-280gsm",
    "https://legendary-branding.com/products/butterfly-tee",
    "https://legendary-branding.com/products/2025-new-hip-hop-fashion-spliced-baggy-jeans-for-men-pleated-design-casual-straight-leg-denim-pants-y2k-vintage-streetwear-jean",
    "https://legendary-branding.com/products/goat-club-atlanta-trucker-hat",
    "https://legendary-branding.com/products/goat-club-texas-trucker-hat",
    "https://legendary-branding.com/products/lil-goat-combed-cotton-regular-fit-t-shirt190gsm",
    "https://legendary-branding.com/products/goat-club-syracuse-trucker-hat",
    "https://legendary-branding.com/products/the-goat-combed-cotton-regular-fit-t-shirt190gsm",
    "https://legendary-branding.com/products/the-goat-premium-polo",
    "https://legendary-branding.com/products/goat-varsity-club-cotton-regular-fit-t-shirt190gsm",
    "https://legendary-branding.com/products/land-of-the-goated-oversized-t-shirt190-gsm",
]

# ── Auth ──────────────────────────────────────────────────────────────────────
SA_KEY_JSON = os.environ.get("GCP_SA_KEY")
if not SA_KEY_JSON:
    print("ERROR: GCP_SA_KEY not set", file=sys.stderr)
    sys.exit(1)

sa_info = json.loads(SA_KEY_JSON)
creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
creds.refresh(GoogleRequest())

BASE_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"

print(f"Requesting indexing for {len(URLS_TO_INDEX)} URLs under {SITE_URL}")
print("=" * 70)

results = {"success": [], "error": []}

for url in URLS_TO_INDEX:
    payload = {"inspectionUrl": url, "siteUrl": SITE_URL}
    resp = requests.post(
        BASE_URL,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type":  "application/json",
        },
        json=payload,
    )

    if resp.status_code == 200:
        verdict = resp.json().get("inspectionResult", {}).get("indexStatusResult", {}).get("verdict", "UNKNOWN")
        print(f"  ✓ [{verdict}] {url.split('/products/')[-1]}")
        results["success"].append(url)
    else:
        print(f"  ✗ ERROR {resp.status_code}: {url}")
        try:
            print(f"    {resp.json().get('error', {}).get('message', resp.text[:200])}")
        except Exception:
            print(f"    {resp.text[:200]}")
        results["error"].append(url)

    time.sleep(1.2)  # stay under quota

print("\n" + "=" * 70)
print(f"Done — success: {len(results['success'])} | errors: {len(results['error'])}")

if results["error"]:
    print("\nFailed URLs:")
    for u in results["error"]:
        print(f"  {u}")
    # Exit 0 even with partial failures — don't block CI
