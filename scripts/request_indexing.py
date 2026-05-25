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

SITE_URL = "https://legendary-branding.com/"
SCOPES   = ["https://www.googleapis.com/auth/webmasters"]

URLS_TO_INDEX = [
    "https://legendary-branding.com/products/legendary-x-champion-r-simple-sweatshirt",
    "https://legendary-branding.com/products/butterfly-tee",
    "https://legendary-branding.com/products/ghosted-tee",
    "https://legendary-branding.com/products/legendary-x-adidas-sport-polo-recycled-pique-hydrophilic-finish",
    "https://legendary-branding.com/products/athletic-department-premium-tank-top-soft-washed-cotton-relaxed-fit",
    "https://legendary-branding.com/products/legendary-world-round-t-shirt",
    "https://legendary-branding.com/products/yellow-dot-athletic-long-short",
    "https://legendary-branding.com/products/goat-denim-t-shirt-lightweight-cotton-tee-soft-touch-streetwear-fit",
    "https://legendary-branding.com/products/legendary-distressed-sweatshirt-washed-ombre-effect-heavyweight-440",
    "https://legendary-branding.com/products/mentality-matters2-heavyweight-washed-boxy-hoodie",
    "https://legendary-branding.com/products/mentality-matters2-unisex-boxy-t-shirt",
    "https://legendary-branding.com/products/mountain-trek-unisex-boxy-t-shirt",
    "https://legendary-branding.com/products/goat-club-syracuse-trucker-hat",
    "https://legendary-branding.com/products/goat-club-texas-trucker-hat",
    "https://legendary-branding.com/products/foam-trucker-hat-with-mesh-panels",
    "https://legendary-branding.com/products/goat-club-atlanta-trucker-hat",
    "https://legendary-branding.com/products/goat-club-chicago-trucker-hat",
    "https://legendary-branding.com/products/unisex-oversized-snow-wash-t-shirt285gsm-2",
    "https://legendary-branding.com/products/unisex-boxy-t-shirt280gsm",
    "https://legendary-branding.com/products/hysteria-cropped-boxy-tank-top-280gsm-1",
    "https://legendary-branding.com/products/summer-vibes-cropped-boxy-tank-top-280gsm",
    "https://legendary-branding.com/products/240gsm-unisex-oversized-drop-shoulders-t-shirt",
    "https://legendary-branding.com/products/santa-barbara-oversized-crewneck-sweatshirt-460gsm",
    "https://legendary-branding.com/products/rose-bowl-oversized-crewneck-sweatshirt-460gsm",
    "https://legendary-branding.com/products/the-lb-hat-foam-trucker-hat",
    "https://legendary-branding.com/products/goat-wrld-loose-fit-t-shirt-190gsm",
    "https://legendary-branding.com/products/goat-sh-t-only-oversized-cropped-t-shirt280gsm",
    "https://legendary-branding.com/products/legendary-fx-oversized-cropped-t-shirt280gsm",
    "https://legendary-branding.com/products/stay-rich-oversized-t-shirt190-gsm",
    "https://legendary-branding.com/products/land-of-the-goated-oversized-t-shirt190-gsm",
    "https://legendary-branding.com/products/legendary-coast-club-oversized-t-shirt190-gsm",
    "https://legendary-branding.com/products/blank-oversized-snow-wash-t-shirt",
    "https://legendary-branding.com/products/blank-washed-gradient-goat-t-shirt",
    "https://legendary-branding.com/products/blank-washed-gradient-t-shirt",
    "https://legendary-branding.com/products/bottom-sunfade-gradient-washed-vintage-goat-t-shirt250gsm",
    "https://legendary-branding.com/products/cropped-snow-washed-goat-t-shirt285gsm",
    "https://legendary-branding.com/products/goat-casual-sweat-shorts280gsm",
    "https://legendary-branding.com/products/goat-speed-boxy-fit-hoodie400gsm",
    "https://legendary-branding.com/products/oversized-heavyweight-hoodie-goat-club-drip",
    "https://legendary-branding.com/products/goated-oversized-heavyweight-sweatshirt-unisex-fleece-crewneck-bold-streetwear-pullover-soft-cotton-blend-cozy-relaxed-fit-drop-shoulder-hoodie-alt",
    "https://legendary-branding.com/products/lil-goat-combed-cotton-regular-fit-t-shirt190gsm",
    "https://legendary-branding.com/products/the-goat-combed-cotton-regular-fit-t-shirt190gsm",
    "https://legendary-branding.com/products/goat-varsity-club-cotton-regular-fit-t-shirt190gsm",
    "https://legendary-branding.com/products/mens-solid-color-oversized-hoodie-jogger-set",
    "https://legendary-branding.com/products/striped-flared-sweatpants-mens-slim-fit-sweatpants",
    "https://legendary-branding.com/products/jeans-men-new-streetwear-baggy-wide-leg-jeans-korean-fashion",
    "https://legendary-branding.com/products/faith-oversized-drop-shoulders-t-shirt",
    "https://legendary-branding.com/products/legendary-wide-leg-sweatpants",
    "https://legendary-branding.com/products/the-goat-premium-polo",
    "https://legendary-branding.com/products/shattered-backboard-oversized-t-shirt190-gsm",
    "https://legendary-branding.com/products/goat-society-chosen-one-oversized-t-shirt190-gsm",
    "https://legendary-branding.com/products/adistar-jellyfish-oversized-t-shirt",
    "https://legendary-branding.com/products/goat-club-oversized-t-shirt",
    "https://legendary-branding.com/products/neverdy-oversized-t-shirt-235gsm",
    "https://legendary-branding.com/products/neverdy-boxy-fit-hoodie",
    "https://legendary-branding.com/products/heavyweight-oversized-hoodie-460gsm",
    "https://legendary-branding.com/products/heavyweight-multi-pocket-jean",
    "https://legendary-branding.com/products/legendary-branding-heavyweight-sweatpants-440gsm",
    "https://legendary-branding.com/products/legendary-branding-fleece-zip-up",
    "https://legendary-branding.com/products/goat-hoodie-440gsm",
    "https://legendary-branding.com/products/no-risk-no-story-oversized-t-shirt",
    "https://legendary-branding.com/products/mini-goat-oversized-t-shirt",
    "https://legendary-branding.com/products/goat-club-spray-painted-oversized-hoodie",
    "https://legendary-branding.com/products/legendary-branding-og-permanent-marker-t-shirt-unisex-heavyweight-40s-combed-cotton-oversized-t-shirt-235gsm",
    "https://legendary-branding.com/products/dawg-pit-bull-oversized-t-shirt",
    "https://legendary-branding.com/products/icon-of-the-herd-combed-cotton-cropped-oversized-t-shirt-250gsm",
    "https://legendary-branding.com/products/the-legendary-heavyweight-oversized-t-shirt",
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
    sys.exit(1)
