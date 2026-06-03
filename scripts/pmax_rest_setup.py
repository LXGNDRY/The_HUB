#!/usr/bin/env python3
"""
pmax_rest_setup.py — Legendary Branding
Creates PMax campaign structure via Google Ads REST API v21.
Auth: OAuth2 access token obtained via google-auth from GCP SA key
      (requires SA email to be added as Google Ads user with Editor role).

If SA does not have Ads API access, set GOOGLE_ADS_ACCESS_TOKEN env var
with a valid OAuth2 access token obtained from Pipedream or Google OAuth playground.

Account:  1137623123
GMC:      582171114

Required env vars (one of two auth modes):
  Mode A (SA auth — if SA has Ads API access):
    GCP_SA_KEY              — service account JSON key
    GOOGLE_ADS_DEVELOPER_TOKEN — developer token from Google Ads API Center

  Mode B (OAuth2 token — direct token):
    GOOGLE_ADS_ACCESS_TOKEN    — OAuth2 bearer token (1hr TTL)
    GOOGLE_ADS_DEVELOPER_TOKEN — developer token

Usage:
  python pmax_rest_setup.py
"""

import os, sys, json, time, requests
from datetime import date

# ── Config ────────────────────────────────────────────────────────────────────
CUSTOMER_ID        = "1137623123"
MERCHANT_ID        = 582171114
CAMPAIGN_NAME      = "LB \u2014 Performance Max \u2014 Streetwear"
DAILY_BUDGET_USD   = 30
START_DATE         = date.today().strftime("%Y-%m-%d")

ADS_API_BASE = "https://googleads.googleapis.com/v21"

# ── Auth ──────────────────────────────────────────────────────────────────────
def get_access_token():
    """Get OAuth2 access token for Google Ads API scope."""
    # Mode B: direct token from env
    token = os.environ.get("GOOGLE_ADS_ACCESS_TOKEN")
    if token:
        print("Using GOOGLE_ADS_ACCESS_TOKEN from env")
        return token

    # Mode A: generate from SA key
    sa_key = os.environ.get("GCP_SA_KEY")
    if sa_key:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleRequest
        print("Generating token from GCP_SA_KEY...")
        creds = service_account.Credentials.from_service_account_info(
            json.loads(sa_key),
            scopes=["https://www.googleapis.com/auth/adwords"],
        )
        creds.refresh(GoogleRequest())
        return creds.token

    print("ERROR: No auth credentials found.")
    print("Set GOOGLE_ADS_ACCESS_TOKEN or GCP_SA_KEY")
    sys.exit(1)

def get_headers():
    token = get_access_token()
    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
    if not dev_token:
        print("ERROR: GOOGLE_ADS_DEVELOPER_TOKEN is required.")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {token}",
        "developer-token": dev_token,
        "Content-Type": "application/json",
    }

def ads_post(path, body):
    """POST to Google Ads REST API."""
    url = f"{ADS_API_BASE}/customers/{CUSTOMER_ID}/{path}"
    r = requests.post(url, headers=get_headers(), json=body)
    if not r.ok:
        print(f"ERROR {r.status_code}: {r.text}")
        r.raise_for_status()
    return r.json()

# ── Search Theme Definitions ───────────────────────────────────────────────────
ASSET_GROUPS = [
    {
        "name": "Heavyweight Tees & Tops",
        "final_url": "https://legendary-branding.com/collections/shirts-tops",
        "themes": [
            "heavyweight oversized t shirt",
            "heavyweight graphic tee streetwear",
            "boxy fit graphic tee",
            "oversized streetwear t shirt mens",
            "premium cotton heavyweight tee",
            "280gsm oversized t shirt",
            "buy graphic tee streetwear",
            "cropped oversized t shirt unisex",
            "premium streetwear tops",
            "drop shoulder graphic tee",
            "luxury streetwear t shirt",
            "oversized boxy tee men",
            "premium heavyweight graphic shirt",
            "streetwear brand t shirt chicago",
            "goat streetwear tee",
            "unisex oversized street tee",
            "heavyweight cotton graphic shirt",
            "streetwear polo shirt boxy",
            "graphic tee alternative",
            "Fear of God Essentials tee alternative",
            "Represent streetwear tee alternative",
            "premium graphic tee under 100",
            "streetwear t shirt brand",
            "bold graphic tee oversized",
            "vintage heavyweight drop tee",
        ],
    },
    {
        "name": "Hoodies & Crewnecks",
        "final_url": "https://legendary-branding.com/collections/hoodies-jackets",
        "themes": [
            "heavyweight oversized hoodie streetwear",
            "460gsm oversized hoodie",
            "boxy fit crewneck sweatshirt",
            "premium streetwear hoodie mens",
            "oversized zip up hoodie",
            "drop shoulder hoodie streetwear",
            "luxury heavyweight hoodie",
            "streetwear crewneck sweatshirt",
            "premium fleece hoodie boxy",
            "oversized pullover hoodie men",
            "buy oversized hoodie streetwear",
            "heavyweight crewneck men",
            "GOAT Club hoodie",
            "Fear of God hoodie alternative",
            "Represent hoodie alternative",
            "boxy hoodie unisex",
            "chunky knit streetwear hoodie",
            "premium cotton crewneck",
            "streetwear brand hoodie chicago",
            "vintage wash oversized hoodie",
            "oversized french terry sweatshirt",
            "heavyweight zip hoodie mens",
            "premium crewneck sweatshirt under 100",
            "streetwear hoodie brand",
            "bold graphic hoodie streetwear",
        ],
    },
    {
        "name": "Pants, Jeans & Sets",
        "final_url": "https://legendary-branding.com/collections/all-products",
        "themes": [
            "baggy streetwear jeans mens",
            "oversized sweatpants streetwear",
            "matching streetwear set",
            "cargo pants streetwear mens",
            "wide leg denim streetwear",
            "jogger sweatpants streetwear brand",
            "baggy fit jeans men",
            "streetwear matching outfit set",
            "premium baggy pants mens",
            "track pants streetwear",
            "oversized sweatsuit set",
            "relaxed fit jeans streetwear",
            "luxury streetwear trousers",
            "buy matching streetwear set",
            "baggy linen pants streetwear",
            "streetwear cargo trousers",
            "premium sweatpants mens brand",
            "streetwear two piece set",
            "GOAT Club pants",
            "Fear of God pants alternative",
            "wide leg trousers streetwear",
            "heavyweight sweatpants brand",
            "relaxed denim streetwear brand",
            "streetwear pants chicago brand",
            "men streetwear coord set",
        ],
    },
    {
        "name": "GOAT Club Brand & Collabs",
        "final_url": "https://legendary-branding.com/collections/all-products",
        "themes": [
            "GOAT Club streetwear",
            "Legendary Branding clothing",
            "LB streetwear brand",
            "GOAT Club hoodie tee",
            "legendary branding chicago",
            "GOAT Club collab drop",
            "legendary branding apparel",
            "GOAT x Champion streetwear",
            "GOAT x Adidas collab",
            "GOAT Club limited drop",
            "legendary branding online store",
            "goat club collection",
            "LB x Champion hoodie",
            "LB premium streetwear",
            "GOAT Club brand merch",
            "legendary branding tee",
            "goat club capsule collection",
            "LB collab apparel",
            "legendary branding hoodie",
            "streetwear brand collab drop",
            "GOAT Club exclusive drop",
            "LB streetwear chicago",
            "legendary branding new drop",
            "goat club crewneck",
            "legendary branding brand apparel",
        ],
    },
    {
        "name": "Accessories & Hats",
        "final_url": "https://legendary-branding.com/collections/accessories-more",
        "themes": [
            "streetwear trucker hat",
            "city trucker hat mens",
            "streetwear snapback hat",
            "premium streetwear cap",
            "Chicago streetwear hat",
            "GOAT Club hat",
            "streetwear accessories men",
            "oversized streetwear beanie",
            "brand logo trucker cap",
            "vintage streetwear hat",
            "buy streetwear hat online",
            "streetwear bucket hat",
            "legendary branding hat",
            "streetwear fitted cap",
            "streetwear socks accessories",
            "brand streetwear accessories",
            "streetwear crossbody bag",
            "streetwear outerwear jacket",
            "premium streetwear jacket mens",
            "GOAT Club accessories",
            "streetwear windbreaker",
            "bomber jacket streetwear brand",
            "streetwear brand hat chicago",
            "streetwear embroidered cap",
            "streetwear accessory bundle",
        ],
    },
]


def create_budget():
    print("\n[1/3] Creating campaign budget...")
    body = {
        "operations": [{
            "create": {
                "name": "LB PMax Streetwear Budget",
                "amountMicros": str(DAILY_BUDGET_USD * 1_000_000),
                "deliveryMethod": "STANDARD",
                "explicitlyShared": False,
            }
        }]
    }
    result = ads_post("campaignBudgets:mutate", body)
    rn = result["results"][0]["resourceName"]
    print(f"  Budget created: {rn}")
    return rn


def create_campaign(budget_rn):
    print("\n[2/3] Creating PMax campaign...")
    body = {
        "operations": [{
            "create": {
                "name": CAMPAIGN_NAME,
                "advertisingChannelType": "PERFORMANCE_MAX",
                "campaignBudget": budget_rn,
                "status": "PAUSED",
                "startDate": START_DATE,
                "maximizeConversionValue": {},
                "shoppingSetting": {
                    "merchantId": MERCHANT_ID,
                    "feedLabel": "US",
                },
            }
        }]
    }
    result = ads_post("campaigns:mutate", body)
    rn = result["results"][0]["resourceName"]
    campaign_id = rn.split("/")[-1]
    print(f"  Campaign created: {rn}")
    print(f"  Campaign ID: {campaign_id}")
    return rn, campaign_id


def create_asset_group_with_themes(campaign_rn, campaign_id, group_def, temp_id):
    """
    Create an asset group (PMax retail — no assets required when linked to GMC).
    Then attach search theme signals.
    """
    name = group_def["name"]
    final_url = group_def["final_url"]
    themes = group_def["themes"]

    # Use GoogleAdsService.mutate for bulk atomic operation
    url = f"{ADS_API_BASE}/customers/{CUSTOMER_ID}/googleAds:mutate"
    
    ag_resource = f"customers/{CUSTOMER_ID}/assetGroups/{temp_id}"
    
    operations = []

    # 1. AssetGroup create
    operations.append({
        "assetGroupOperation": {
            "create": {
                "resourceName": ag_resource,
                "campaign": campaign_rn,
                "name": name,
                "finalUrls": [final_url],
                "status": "ENABLED",
            }
        }
    })

    # 2. Listing group filter (all products) — required for retail PMax
    operations.append({
        "assetGroupListingGroupFilterOperation": {
            "create": {
                "assetGroup": ag_resource,
                "type": "UNIT_INCLUDED",
                "verticalAssetCombinationIdFilter": {},
            }
        }
    })

    # 3. Search theme signals (AssetGroupSignal with search_theme)
    for theme_text in themes:
        operations.append({
            "assetGroupSignalOperation": {
                "create": {
                    "assetGroup": ag_resource,
                    "searchTheme": {
                        "text": theme_text
                    }
                }
            }
        })

    body = {"mutateOperations": operations}
    r = requests.post(url, headers=get_headers(), json=body)
    if not r.ok:
        print(f"  ERROR creating asset group '{name}': {r.status_code} {r.text[:300]}")
        return None
    
    result = r.json()
    print(f"  Asset group '{name}' created with {len(themes)} search themes")
    return result


def main():
    print("=" * 60)
    print("LB PMax Campaign Setup — REST API")
    print("=" * 60)
    print(f"  Customer ID: {CUSTOMER_ID}")
    print(f"  Merchant ID: {MERCHANT_ID}")
    print(f"  Campaign:    {CAMPAIGN_NAME}")
    print(f"  Budget:      ${DAILY_BUDGET_USD}/day")
    print(f"  Start date:  {START_DATE}")
    print(f"  Asset groups: {len(ASSET_GROUPS)}")
    print(f"  Themes total: {sum(len(g['themes']) for g in ASSET_GROUPS)}")

    # Step 1: Budget
    budget_rn = create_budget()

    # Step 2: Campaign  
    campaign_rn, campaign_id = create_campaign(budget_rn)

    # Step 3: Asset groups + search themes
    print(f"\n[3/3] Creating {len(ASSET_GROUPS)} asset groups + search themes...")
    temp_id_start = -1000
    for i, group in enumerate(ASSET_GROUPS):
        temp_id = temp_id_start - i
        result = create_asset_group_with_themes(campaign_rn, campaign_id, group, temp_id)
        if result is None:
            print(f"  ⚠️  Asset group {i+1} failed — continuing with next")
        time.sleep(0.5)  # Rate limit buffer

    print("\n" + "=" * 60)
    print("✅ SETUP COMPLETE")
    print("=" * 60)
    print(f"  Campaign ID: {campaign_id}")
    print(f"  Status: PAUSED (enable in Google Ads UI when ready)")
    print(f"  Budget: ${DAILY_BUDGET_USD}/day")
    print(f"  Link: https://ads.google.com/aw/campaigns?campaignId={campaign_id}&__c={CUSTOMER_ID}")
    print()
    print("Next steps:")
    print("  1. Upload assets (headlines, descriptions, images, logo) in Google Ads UI")
    print("  2. Verify GMC link shows products in the campaign")
    print("  3. Set conversion goals")
    print("  4. Enable campaign when ready to spend")


if __name__ == "__main__":
    main()
