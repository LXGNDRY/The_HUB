#!/usr/bin/env python3
"""
pmax_geo_expand.py — Legendary Branding
Adds geo-targeting criteria to the existing PMax campaign for international markets.
Targets: IN (India), GB (UK), CA (Canada), AU (Australia), DE (Germany)

The campaign previously had no explicit geo-targets (defaulting to all locations).
This script sets explicit positive geo-targets so Smart Bidding can allocate budget
to markets where we now have working shipping rates and Unified Markets pricing.

Auth: GOOGLE_ADS_DEVELOPER_TOKEN + GOOGLE_ADS_CLIENT_ID/SECRET/REFRESH_TOKEN
Account: 1137623123

Usage:
  python scripts/pmax_geo_expand.py

Required env vars:
  GOOGLE_ADS_DEVELOPER_TOKEN
  GOOGLE_ADS_CLIENT_ID
  GOOGLE_ADS_CLIENT_SECRET
  GOOGLE_ADS_REFRESH_TOKEN
"""

import os
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

CUSTOMER_ID = "1137623123"
CAMPAIGN_NAME = "LB — Performance Max — Streetwear"

# Google Ads geo target constant IDs (canonical resource name format)
# These are stable GeoTargetConstant IDs for country-level targeting
GEO_TARGETS = {
    "United States": "geoTargetConstants/2840",
    "India":         "geoTargetConstants/2356",
    "United Kingdom": "geoTargetConstants/2826",
    "Canada":        "geoTargetConstants/2124",
    "Australia":     "geoTargetConstants/2036",
    "Germany":       "geoTargetConstants/2276",
}


def build_client() -> GoogleAdsClient:
    config = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": CUSTOMER_ID,
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(config)


def find_campaign_resource_name(client: GoogleAdsClient) -> str:
    """Find the resource name of the PMax campaign by name."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign.id, campaign.name, campaign.resource_name
        FROM campaign
        WHERE campaign.name = '{CAMPAIGN_NAME}'
          AND campaign.status != 'REMOVED'
        LIMIT 1
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    for row in response:
        print(f"Found campaign: {row.campaign.name} (id={row.campaign.id})")
        return row.campaign.resource_name
    raise ValueError(f"Campaign '{CAMPAIGN_NAME}' not found in account {CUSTOMER_ID}")


def get_existing_geo_targets(client: GoogleAdsClient, campaign_resource_name: str) -> set:
    """Return set of geo target constant resource names already on the campaign."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign_criterion.resource_name, campaign_criterion.location.geo_target_constant
        FROM campaign_criterion
        WHERE campaign_criterion.campaign = '{campaign_resource_name}'
          AND campaign_criterion.type = 'LOCATION'
          AND campaign_criterion.negative = false
    """
    existing = set()
    try:
        for row in ga_service.search(customer_id=CUSTOMER_ID, query=query):
            existing.add(row.campaign_criterion.location.geo_target_constant)
    except Exception as e:
        print(f"Warning: could not query existing geo targets: {e}")
    return existing


def add_geo_targets(client: GoogleAdsClient, campaign_resource_name: str):
    existing = get_existing_geo_targets(client, campaign_resource_name)
    print(f"Existing geo targets: {existing or '(none — was targeting all locations)'}")

    cc_service = client.get_service("CampaignCriterionService")
    operations = []

    for country, geo_constant in GEO_TARGETS.items():
        if geo_constant in existing:
            print(f"  Skip {country} — already targeted")
            continue

        op = client.get_type("CampaignCriterionOperation")
        criterion = op.create
        criterion.campaign = campaign_resource_name
        criterion.negative = False
        criterion.location.geo_target_constant = geo_constant
        operations.append(op)
        print(f"  Adding {country} ({geo_constant})")

    if not operations:
        print("All geo targets already set. Nothing to do.")
        return

    response = cc_service.mutate_campaign_criteria(
        customer_id=CUSTOMER_ID, operations=operations
    )
    print(f"\nAdded {len(response.results)} geo target(s):")
    for result in response.results:
        print(f"  {result.resource_name}")


def main():
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if dry_run:
        print("[DRY RUN] Would add geo targets for: " + ", ".join(GEO_TARGETS.keys()))
        return

    client = build_client()
    campaign_resource_name = find_campaign_resource_name(client)
    add_geo_targets(client, campaign_resource_name)
    print("\nDone. PMax campaign now targets: " + ", ".join(GEO_TARGETS.keys()))
    print("Monitor ROAS per country in Google Ads → Campaigns → Locations for 14 days.")
    print("Scale rule: ROAS > 2.5x for 2 consecutive weeks → increase daily budget by $5.")


if __name__ == "__main__":
    try:
        main()
    except GoogleAdsException as ex:
        for error in ex.failure.errors:
            print(f"Google Ads error: {error.message}")
            if error.location:
                for fve in error.location.field_value_errors:
                    print(f"  Field: {fve.field_name}")
        sys.exit(1)
