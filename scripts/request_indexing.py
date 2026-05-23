#!/usr/bin/env python3
"""
request_indexing.py
Uses the Google Search Console URL Inspection API to request indexing
for URLs that are "Crawled - currently not indexed".
Requires GSC_TOKEN_JSON env var (OAuth2 token JSON with webmasters scope).
"""

import os, json, time, sys
import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SITE_URL = "sc-domain:legendary-branding.com"

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

# Load OAuth2 credentials from env
token_json = os.environ.get("GSC_TOKEN_JSON")
if not token_json:
    print("ERROR: GSC_TOKEN_JSON not set", file=sys.stderr)
    sys.exit(1)

token_data = json.loads(token_json)
creds = Credentials(
    token=token_data.get("token"),
    refresh_token=token_data.get("refresh_token"),
    token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
    client_id=token_data.get("client_id"),
    client_secret=token_data.get("client_secret"),
    scopes=["https://www.googleapis.com/auth/webmasters"],
)

# Refresh if expired
if not creds.valid:
    creds.refresh(Request())
    print("Token refreshed.")

BASE_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"

print(f"Requesting indexing for {len(URLS_TO_INDEX)} URLs under {SITE_URL}\n")
print("=" * 70)

results = {"success": [], "already_indexed": [], "failed": []}

for url in URLS_TO_INDEX:
    payload = {
        "inspectionUrl": url,
        "siteUrl": SITE_URL,
        "languageCode": "en-US",
    }
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(BASE_URL, json=payload, headers=headers)

    if resp.status_code == 200:
        data = resp.json()
        index_status = data.get("inspectionResult", {}).get("indexStatusResult", {})
        coverage = index_status.get("coverageState", "UNKNOWN")
        verdict = index_status.get("verdict", "UNKNOWN")
        
        # Request indexing via the robotsTxtState and verdict
        if verdict == "PASS" and "Indexed" in coverage:
            print(f"  ✓ ALREADY INDEXED: {url}")
            print(f"    Coverage: {coverage}")
            results["already_indexed"].append(url)
        else:
            # Trigger indexing request
            req_resp = requests.post(
                f"https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
                json={**payload, "requestIndexing": True},
                headers=headers
            )
            if req_resp.status_code == 200:
                print(f"  → INDEXING REQUESTED: {url}")
                print(f"    Coverage was: {coverage} | Verdict: {verdict}")
                results["success"].append(url)
            else:
                print(f"  ✗ REQUEST FAILED: {url}")
                print(f"    Status: {req_resp.status_code} | {req_resp.text[:200]}")
                results["failed"].append(url)
    elif resp.status_code == 403:
        print(f"  ✗ PERMISSION DENIED: {url}")
        print(f"    Make sure the service account has verified access to {SITE_URL}")
        results["failed"].append(url)
    else:
        print(f"  ✗ ERROR {resp.status_code}: {url}")
        print(f"    {resp.text[:200]}")
        results["failed"].append(url)

    time.sleep(1)  # Respect rate limits

print("\n" + "=" * 70)
print(f"SUMMARY:")
print(f"  Indexing requested: {len(results['success'])}")
print(f"  Already indexed:    {len(results['already_indexed'])}")
print(f"  Failed:             {len(results['failed'])}")

if results["failed"]:
    print("\nFailed URLs:")
    for u in results["failed"]:
        print(f"  - {u}")

print("\nDone.")
