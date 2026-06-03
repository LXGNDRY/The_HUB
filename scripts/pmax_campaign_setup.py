#!/usr/bin/env python3
"""
pmax_campaign_setup.py — Legendary Branding
Creates a full Performance Max campaign structure via Google Ads API:
  - Campaign budget
  - PMax campaign (PAUSED — review before enabling)
  - 5 asset groups (Tees, Hoodies, Pants/Sets, Brand, Accessories)
  - 25 search themes per asset group (125 total)
  - Listing group filter (all products) per asset group

The campaign is created in PAUSED status. Enable it manually in
Google Ads UI after reviewing budget, bidding, and asset uploads.

Auth:     GOOGLE_ADS_DEVELOPER_TOKEN + GOOGLE_ADS_CLIENT_ID/SECRET/REFRESH_TOKEN
Account:  1137623123
GMC:      582171114

Usage:
  python pmax_campaign_setup.py

Required secrets (GitHub Actions / local env):
  GOOGLE_ADS_DEVELOPER_TOKEN
  GOOGLE_ADS_CLIENT_ID
  GOOGLE_ADS_CLIENT_SECRET
  GOOGLE_ADS_REFRESH_TOKEN
"""

import os
import sys
import uuid
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# ── Config ────────────────────────────────────────────────────────────────────
CUSTOMER_ID    = "1137623123"
MERCHANT_ID    = "582171114"
CAMPAIGN_NAME  = "LB — Performance Max — Streetwear"
DAILY_BUDGET   = 30_000_000   # $30/day in micros (1,000,000 = $1)
STORE_URL      = "https://legendary-branding.com"

# ── Asset Group Definitions ───────────────────────────────────────────────────
# Each group: (name, final_url, search_themes[25])
ASSET_GROUPS = [
    (
        "Heavyweight Tees & Tops",
        f"{STORE_URL}/collections/shirts-tops",
        [
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
    ),
    (
        "Hoodies & Crewnecks",
        f"{STORE_URL}/collections/hoodies-jackets",
        [
            "heavyweight oversized hoodie streetwear",
            "460gsm oversized hoodie",
            "premium fleece oversized hoodie mens",
            "boxy fit hoodie streetwear",
            "buy oversized hoodie premium",
            "heavyweight graphic hoodie",
            "streetwear hoodie brand",
            "luxury streetwear hoodie",
            "oversized crewneck sweatshirt heavyweight",
            "premium streetwear hoodie men",
            "heavyweight hoodie drop shoulder",
            "zip up streetwear hoodie",
            "oversized fleece hoodie boxy",
            "streetwear crewneck sweatshirt",
            "premium hoodie alternative",
            "Fear of God hoodie alternative",
            "Essentials hoodie dupe",
            "Represent hoodie alternative",
            "heavyweight embroidered sweatshirt",
            "distressed washed hoodie streetwear",
            "neverdy hoodie",
            "goat club hoodie",
            "matching hoodie jogger set",
            "streetwear hoodie under 160",
            "graphic hoodie oversized fit",
        ],
    ),
    (
        "Pants, Jeans & Sets",
        f"{STORE_URL}/collections/all-products",
        [
            "baggy streetwear jeans men",
            "wide leg denim streetwear",
            "heavyweight sweatpants streetwear",
            "baggy fit jeans men",
            "premium streetwear sweatpants",
            "stacked denim jeans streetwear",
            "rhinestone stacked jeans men",
            "wide leg sweatpants premium",
            "matching hoodie sweatpants set",
            "streetwear jogger set unisex",
            "oversized hoodie jogger set",
            "flare sweatpants streetwear",
            "baggy jeans brand streetwear",
            "premium denim streetwear men",
            "buy streetwear sweatpants",
            "heavyweight jogger pants streetwear",
            "440gsm sweatpants premium",
            "streetwear matching set",
            "Korean fashion baggy jeans",
            "streetwear pants brand",
            "premium streetwear bottoms",
            "baggy wide leg pants men",
            "streetwear outfit set unisex",
            "jogger sweatpants premium brand",
            "streetwear jeans alternative",
        ],
    ),
    (
        "GOAT Club Brand & Collabs",
        f"{STORE_URL}/collections/all-products",
        [
            "legendary branding streetwear",
            "goat club clothing brand",
            "legendary branding hoodie",
            "legendary branding t shirt",
            "lb streetwear brand",
            "legendary branding chicago",
            "buy legendary branding",
            "neverdy streetwear brand",
            "goat club apparel",
            "legendary x champion hoodie",
            "champion collab streetwear",
            "legendary x adidas polo",
            "adidas collab streetwear",
            "independent streetwear brand",
            "premium chicago streetwear",
            "goat theme clothing",
            "legendary branding collection",
            "emerging streetwear brand",
            "streetwear brand like fear of god",
            "luxury streetwear brand chicago",
            "premium independent clothing brand",
            "goat club hoodie brand",
            "iconic streetwear brand",
            "goat club spray painted hoodie",
            "legendary branding shop online",
        ],
    ),
    (
        "Accessories & Hats",
        f"{STORE_URL}/collections/accessories-more",
        [
            "streetwear trucker hat",
            "goat club trucker hat",
            "premium trucker hat streetwear brand",
            "foam trucker hat brand",
            "streetwear hat unisex",
            "city trucker hat streetwear",
            "legendary branding hat",
            "streetwear accessories brand",
            "streetwear baseball cap",
            "buy trucker hat streetwear",
            "athletic shorts streetwear",
            "premium athletic shorts men",
            "water resistant streetwear jacket",
            "champion collab jacket",
            "streetwear outerwear premium",
            "windbreaker streetwear brand",
            "micro poplin jacket streetwear",
            "premium streetwear outerwear",
            "city streetwear hat chicago",
            "new york goat hat",
            "atlanta streetwear hat",
            "california streetwear brand hat",
            "snap back streetwear hat",
            "goat club chicago hat",
            "streetwear trucker cap brand",
        ],
    ),
]

# ── Google Ads Client Setup ───────────────────────────────────────────────────
def get_client():
    """Build GoogleAdsClient from environment secrets."""
    config = {
        "developer_token":  os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id":        os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret":    os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token":    os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": CUSTOMER_ID,
        "use_proto_plus":   True,
    }
    return GoogleAdsClient.load_from_dict(config)


def temp_id():
    """Generate a unique negative temp ID for bulk mutate operations."""
    temp_id.counter -= 1
    return temp_id.counter
temp_id.counter = -1


def err(ex: GoogleAdsException):
    print(f"\nGoogle Ads API Error: {ex.error.code().name}")
    for error in ex.failure.errors:
        print(f"  [{error.error_code}] {error.message}")
        if error.location:
            for fve in error.location.field_value_errors:
                print(f"    Field: {fve.field_name}")
    sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    client  = get_client()
    gads    = client.get_service("GoogleAdsService")
    mutate  = client.get_service("GoogleAdsMutateService")  # used for batched mutate

    campaign_service     = client.get_service("CampaignService")
    budget_service       = client.get_service("CampaignBudgetService")
    asset_group_service  = client.get_service("AssetGroupService")
    signal_service       = client.get_service("AssetGroupSignalService")
    listing_service      = client.get_service("AssetGroupListingGroupFilterService")

    print("=" * 70)
    print("LEGENDARY BRANDING — PMAX CAMPAIGN SETUP")
    print("=" * 70)
    print(f"  Account  : {CUSTOMER_ID}")
    print(f"  Merchant : {MERCHANT_ID}")
    print(f"  Budget   : ${DAILY_BUDGET / 1_000_000:.2f}/day")
    print(f"  Status   : PAUSED (enable manually after review)")
    print()

    # ── Step 1: Create campaign budget ───────────────────────────────────────
    print("STEP 1: Creating campaign budget...")
    budget_op = client.get_type("CampaignBudgetOperation")
    budget    = budget_op.create
    budget.name                    = f"LB PMax Budget — {uuid.uuid4().hex[:6]}"
    budget.amount_micros           = DAILY_BUDGET
    budget.delivery_method         = client.enums.BudgetDeliveryMethodEnum.STANDARD
    budget.explicitly_shared       = False

    try:
        budget_resp  = budget_service.mutate_campaign_budgets(
            customer_id=CUSTOMER_ID, operations=[budget_op]
        )
        budget_rname = budget_resp.results[0].resource_name
        print(f"  Budget created: {budget_rname}")
    except GoogleAdsException as ex:
        err(ex)

    # ── Step 2: Create PMax campaign ─────────────────────────────────────────
    print("\nSTEP 2: Creating Performance Max campaign (PAUSED)...")
    camp_op   = client.get_type("CampaignOperation")
    campaign  = camp_op.create
    campaign.name                      = CAMPAIGN_NAME
    campaign.advertising_channel_type  = (
        client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
    )
    campaign.status                    = client.enums.CampaignStatusEnum.PAUSED
    campaign.campaign_budget           = budget_rname
    campaign.bidding_strategy_type     = (
        client.enums.BiddingStrategyTypeEnum.MAXIMIZE_CONVERSION_VALUE
    )

    # Link to GMC merchant center
    campaign.shopping_setting.merchant_id       = int(MERCHANT_ID)
    campaign.shopping_setting.feed_label        = "US"
    campaign.shopping_setting.enable_local      = False

    try:
        camp_resp   = campaign_service.mutate_campaigns(
            customer_id=CUSTOMER_ID, operations=[camp_op]
        )
        campaign_rname = camp_resp.results[0].resource_name
        print(f"  Campaign created: {campaign_rname}")
    except GoogleAdsException as ex:
        err(ex)

    # ── Step 3: Create asset groups + search themes ───────────────────────────
    print("\nSTEP 3: Creating asset groups + search themes...")

    for ag_name, final_url, themes in ASSET_GROUPS:
        print(f"\n  [{ag_name}]")

        # Create asset group
        ag_op     = client.get_type("AssetGroupOperation")
        ag        = ag_op.create
        ag.name   = ag_name
        ag.campaign = campaign_rname
        ag.status = client.enums.AssetGroupStatusEnum.PAUSED
        ag.final_urls.append(final_url)
        ag.final_mobile_urls.append(final_url)

        try:
            ag_resp   = asset_group_service.mutate_asset_groups(
                customer_id=CUSTOMER_ID, operations=[ag_op]
            )
            ag_rname  = ag_resp.results[0].resource_name
            print(f"    Asset group: {ag_rname}")
        except GoogleAdsException as ex:
            err(ex)

        # Add listing group filter (catch-all — all products)
        lgf_op  = client.get_type("AssetGroupListingGroupFilterOperation")
        lgf     = lgf_op.create
        lgf.asset_group  = ag_rname
        lgf.type_        = (
            client.enums.ListingGroupFilterTypeEnum.UNIT_INCLUDED
        )
        lgf.vertical     = (
            client.enums.ListingGroupFilterVerticalEnum.SHOPPING
        )

        try:
            listing_service.mutate_asset_group_listing_group_filters(
                customer_id=CUSTOMER_ID, operations=[lgf_op]
            )
            print(f"    Listing group filter added (all products)")
        except GoogleAdsException as ex:
            print(f"    Warning: listing group filter error — {ex.failure.errors[0].message}")

        # Add search themes (25 per group)
        signal_ops = []
        for theme_text in themes:
            sig_op  = client.get_type("AssetGroupSignalOperation")
            sig     = sig_op.create
            sig.asset_group   = ag_rname
            sig.search_theme.text = theme_text
            signal_ops.append(sig_op)

        try:
            sig_resp = signal_service.mutate_asset_group_signals(
                customer_id=CUSTOMER_ID, operations=signal_ops
            )
            approved = 0
            pending  = 0
            declined = 0
            for r in sig_resp.results:
                status = str(r).lower()
                if "approved" in status:  approved += 1
                elif "pending" in status: pending  += 1
                else:                     declined += 1
            print(f"    {len(signal_ops)} search themes added "
                  f"(approved={approved}, pending={pending}, declined={declined})")
        except GoogleAdsException as ex:
            err(ex)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PMAX CAMPAIGN SETUP COMPLETE")
    print("=" * 70)
    print(f"  Campaign     : {CAMPAIGN_NAME}")
    print(f"  Resource     : {campaign_rname}")
    print(f"  Status       : PAUSED — enable in Google Ads UI after:")
    print(f"                  1. Upload headlines/descriptions/images to each asset group")
    print(f"                  2. Verify GMC feed is clean (run gmc-audit)")
    print(f"                  3. Set conversion actions in Google Ads")
    print(f"                  4. Review budget ($30/day recommended start)")
    print()
    print(f"  Asset groups : {len(ASSET_GROUPS)}")
    print(f"  Search themes: {len(ASSET_GROUPS) * 25} total (25 per group)")
    print()
    print(f"  ASSET GROUPS CREATED:")
    for ag_name, url, themes in ASSET_GROUPS:
        print(f"    - {ag_name}  →  {url}")
    print()
    print("  NEXT STEPS (manual in Google Ads UI):")
    print("    1. Add headlines (15), descriptions (5), images (20) per asset group")
    print("    2. Add brand exclusion: 'Legendary Branding' brand list")
    print("       (prevents wasted spend on existing brand searches)")
    print("    3. Add campaign-level negative keywords:")
    print("       [free, diy, how to make, costume, cosplay]")
    print("    4. Set target ROAS or Maximize Conversion Value bidding goal")
    print("    5. Link GA4 property 461293086 as conversion source")
    print("    6. Enable campaign when account has 30+ day data window")


if __name__ == "__main__":
    main()
