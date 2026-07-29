#!/usr/bin/env python3
"""
pmax_exclude_placements.py — Legendary Branding
Creates a shared negative placement list and attaches it to the LXGNDRY
PMax campaign to block low-quality display/syndication domains that have
been driving sessions into checkout with zero conversions.

What this does:
  1. Creates (or reuses) a SharedSet named "LB — Negative Placements"
  2. Adds all junk domains to it as negative placement criteria
  3. Attaches the SharedSet to every ENABLED PMax campaign in the account
     (or a specific campaign ID if --campaign-id is passed)

Domains blocked:
  googlesyndication.com   — Google AdSense display placements (322 sessions, 0 conv)
  syndicatedsearch.com    — Google search syndication partners (128 sessions, 0 conv)
  sportsseier.com         — 35 sessions, 0 conv
  lsmagazineimg.com       — 27 sessions, 0 conv
  dreametrip.com          — 18 sessions, 0 conv
  dreamforge.com          — 14 sessions, 0 conv
  scorenga.com            — junk placement, 0 conv
  glance.com              — 13 sessions, 0 conv
  taboolanews.com         — 10 sessions, 0 conv
  ecer.com                — 8 sessions, 0 conv
  best-jobs-online.com    — 4 sessions, 0 conv
  defenddaily.com         — 2 sessions, 0 conv

Auth: same as pmax_report.py
  GOOGLE_ADS_DEVELOPER_TOKEN
  GOOGLE_ADS_CLIENT_ID
  GOOGLE_ADS_CLIENT_SECRET
  GOOGLE_ADS_REFRESH_TOKEN

Usage:
  python scripts/pmax_exclude_placements.py              # apply to all ENABLED PMax campaigns
  python scripts/pmax_exclude_placements.py --dry-run    # print plan, make no changes
  python scripts/pmax_exclude_placements.py --campaign-id 23907560337  # specific campaign
  python scripts/pmax_exclude_placements.py --list       # list existing shared placement sets
"""

import os
import sys
import argparse
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# ── Config ─────────────────────────────────────────────────────────────────────
CUSTOMER_ID    = "1137623123"
SHARED_SET_NAME = "LB — Negative Placements"

JUNK_DOMAINS = [
    "googlesyndication.com",
    "syndicatedsearch.com",
    "sportsseier.com",
    "lsmagazineimg.com",
    "dreametrip.com",
    "dreamforge.com",
    "scorenga.com",
    "glance.com",
    "taboolanews.com",
    "ecer.com",
    "best-jobs-online.com",
    "defenddaily.com",
]

# ── Client ─────────────────────────────────────────────────────────────────────

def get_client():
    config = {
        "developer_token":   os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id":         os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret":     os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token":     os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": CUSTOMER_ID,
        "use_proto_plus":    True,
    }
    return GoogleAdsClient.load_from_dict(config)


# ── Step 1: find or create the shared negative placement set ───────────────────

def find_existing_shared_set(client):
    """Return (resource_name, id) of existing LB — Negative Placements set, or None."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT shared_set.id, shared_set.name, shared_set.resource_name
        FROM shared_set
        WHERE shared_set.type = 'NEGATIVE_PLACEMENTS'
          AND shared_set.name = '{SHARED_SET_NAME}'
          AND shared_set.status = 'ENABLED'
        LIMIT 1
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    rows = list(response)
    if rows:
        ss = rows[0].shared_set
        return ss.resource_name, str(ss.id)
    return None, None


def create_shared_set(client, dry_run: bool):
    """Create the negative placement SharedSet and return its resource_name."""
    if dry_run:
        print("  [DRY RUN] Would create SharedSet:", SHARED_SET_NAME)
        return "customers/{}/sharedSets/DRY_RUN".format(CUSTOMER_ID)

    ss_service = client.get_service("SharedSetService")
    op = client.get_type("SharedSetOperation")
    ss = op.create
    ss.name = SHARED_SET_NAME
    ss.type_ = client.enums.SharedSetTypeEnum.NEGATIVE_PLACEMENTS

    response = ss_service.mutate_shared_sets(
        customer_id=CUSTOMER_ID, operations=[op]
    )
    rname = response.results[0].resource_name
    print(f"  Created SharedSet: {rname}")
    return rname


# ── Step 2: get existing placements already in the set ────────────────────────

def get_existing_placements(client, shared_set_resource: str):
    """Return set of domains already in the shared set."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT shared_criterion.placement.url
        FROM shared_criterion
        WHERE shared_criterion.shared_set = '{shared_set_resource}'
          AND shared_criterion.type = 'PLACEMENT'
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    existing = set()
    for r in response:
        url = r.shared_criterion.placement.url
        if url:
            # Normalize: strip leading https://www. for comparison
            existing.add(url.lstrip("https://").lstrip("http://").lstrip("www."))
    return existing


# ── Step 3: add placements to the shared set ───────────────────────────────────

def add_placements(client, shared_set_resource: str, domains: list, dry_run: bool):
    """Add each domain as a negative placement criterion to the shared set."""
    if not domains:
        print("  All domains already present — nothing to add.")
        return

    sc_service = client.get_service("SharedCriterionService")

    ops = []
    for domain in domains:
        url = f"https://{domain}"
        op = client.get_type("SharedCriterionOperation")
        sc = op.create
        sc.shared_set = shared_set_resource
        sc.type_ = client.enums.CriterionTypeEnum.PLACEMENT
        sc.placement.url = url
        ops.append(op)

    if dry_run:
        for domain in domains:
            print(f"  [DRY RUN] Would add placement: https://{domain}")
        return

    response = sc_service.mutate_shared_criteria(
        customer_id=CUSTOMER_ID, operations=ops
    )
    for r in response.results:
        print(f"  Added: {r.resource_name}")


# ── Step 4: find PMax campaigns to attach the set to ──────────────────────────

def get_pmax_campaigns(client, campaign_id_override=None):
    """Return list of (resource_name, id, name) for ENABLED PMax campaigns."""
    ga_service = client.get_service("GoogleAdsService")

    if campaign_id_override:
        where = f"campaign.id = {campaign_id_override}"
    else:
        where = "campaign.advertising_channel_type = 'PERFORMANCE_MAX' AND campaign.status = 'ENABLED'"

    query = f"""
        SELECT campaign.id, campaign.name, campaign.resource_name
        FROM campaign
        WHERE {where}
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    return [(r.campaign.resource_name, str(r.campaign.id), r.campaign.name) for r in response]


# ── Step 5: check if the set is already attached to a campaign ────────────────

def get_attached_shared_sets(client, campaign_resource: str):
    """Return set of shared_set resource names already attached to the campaign."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign_shared_set.shared_set
        FROM campaign_shared_set
        WHERE campaign_shared_set.campaign = '{campaign_resource}'
          AND campaign_shared_set.status = 'ENABLED'
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    return {r.campaign_shared_set.shared_set for r in response}


# ── Step 6: attach shared set to campaign ─────────────────────────────────────

def attach_shared_set(client, campaign_resource: str, shared_set_resource: str,
                      campaign_name: str, dry_run: bool):
    if dry_run:
        print(f"  [DRY RUN] Would attach shared set to: {campaign_name}")
        return

    css_service = client.get_service("CampaignSharedSetService")
    op = client.get_type("CampaignSharedSetOperation")
    css = op.create
    css.campaign = campaign_resource
    css.shared_set = shared_set_resource

    css_service.mutate_campaign_shared_sets(
        customer_id=CUSTOMER_ID, operations=[op]
    )
    print(f"  Attached to campaign: {campaign_name}")


# ── List mode ──────────────────────────────────────────────────────────────────

def list_shared_sets(client):
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT shared_set.id, shared_set.name, shared_set.member_count, shared_set.type
        FROM shared_set
        WHERE shared_set.type = 'NEGATIVE_PLACEMENTS'
          AND shared_set.status = 'ENABLED'
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    rows = list(response)
    if not rows:
        print("  No negative placement shared sets found.")
        return
    print(f"\n  {'Name':<40} {'ID':<15} {'Members':>8}")
    print("  " + "-" * 66)
    for r in rows:
        ss = r.shared_set
        print(f"  {ss.name:<40} {str(ss.id):<15} {ss.member_count:>8}")


# ── Main ───────────────────────────────────────────────────────────────────────

def section(title):
    print()
    print("=" * 68)
    print(f"  {title}")
    print("=" * 68)


def main():
    parser = argparse.ArgumentParser(description="Add negative placement exclusions to PMax")
    parser.add_argument("--dry-run",     action="store_true", help="Print plan without making changes")
    parser.add_argument("--campaign-id", type=str, default=None, help="Target a specific campaign ID")
    parser.add_argument("--list",        action="store_true", help="List existing negative placement sets and exit")
    args = parser.parse_args()

    print()
    print("  Connecting to Google Ads API...")
    client = get_client()

    if args.list:
        section("EXISTING NEGATIVE PLACEMENT SHARED SETS")
        list_shared_sets(client)
        print()
        return

    if args.dry_run:
        print("  *** DRY RUN — no changes will be made ***")

    # ── 1. Shared set ──────────────────────────────────────────────────────────
    section("STEP 1 — Shared Negative Placement Set")
    existing_rname, existing_id = find_existing_shared_set(client)

    if existing_rname:
        shared_set_resource = existing_rname
        print(f"  Found existing set: '{SHARED_SET_NAME}' (ID: {existing_id})")
    else:
        print(f"  Set '{SHARED_SET_NAME}' not found — creating...")
        shared_set_resource = create_shared_set(client, args.dry_run)

    # ── 2. Placements ──────────────────────────────────────────────────────────
    section("STEP 2 — Adding Placement Exclusions")
    if args.dry_run or "DRY_RUN" in shared_set_resource:
        already_present = set()
    else:
        already_present = get_existing_placements(client, shared_set_resource)

    to_add = []
    for domain in JUNK_DOMAINS:
        normalized = domain.lstrip("www.")
        if normalized in already_present or domain in already_present:
            print(f"  Already present: {domain}")
        else:
            to_add.append(domain)

    add_placements(client, shared_set_resource, to_add, args.dry_run)

    # ── 3. Campaign attachment ─────────────────────────────────────────────────
    section("STEP 3 — Attaching to PMax Campaigns")
    campaigns = get_pmax_campaigns(client, args.campaign_id)

    if not campaigns:
        target = f"campaign ID {args.campaign_id}" if args.campaign_id else "any ENABLED PMax campaigns"
        print(f"  No campaigns found matching: {target}")
        sys.exit(1)

    for camp_rname, camp_id, camp_name in campaigns:
        print(f"\n  Campaign: {camp_name} (ID: {camp_id})")
        if not args.dry_run and "DRY_RUN" not in shared_set_resource:
            already_attached = get_attached_shared_sets(client, camp_rname)
            if shared_set_resource in already_attached:
                print("    Already attached — skipping.")
                continue
        attach_shared_set(client, camp_rname, shared_set_resource, camp_name, args.dry_run)

    # ── Summary ────────────────────────────────────────────────────────────────
    section("DONE")
    if args.dry_run:
        print("  Dry run complete — re-run without --dry-run to apply changes.")
    else:
        print(f"  {len(JUNK_DOMAINS)} domains blocked across {len(campaigns)} campaign(s).")
        print()
        print("  Next steps:")
        print("    1. In Google Ads UI → Shared Library → Placement exclusion lists")
        print(f"       verify '{SHARED_SET_NAME}' is present with correct member count.")
        print("    2. Confirm the list is attached under:")
        print("       Campaign → Settings → Placements → Exclusions")
        print("    3. Monitor conversion rate over next 7 days —")
        print("       display/syndication junk traffic should drop sharply.")
    print()


if __name__ == "__main__":
    main()
