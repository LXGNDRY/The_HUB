#!/usr/bin/env python3
"""
pmax_report.py — Legendary Branding
Pulls live performance data for the LXGNDRY Performance Max campaign
from the Google Ads API and prints a structured report.

Metrics pulled:
  - Impressions, Clicks, CTR, Avg CPC, Cost, Conversions, Conv. Value
  - Daily breakdown (last N days, default 14)
  - Asset group breakdown
  - Campaign-level status + bidding strategy
  - Search theme performance (top/bottom signals)
  - Payment stack readiness note (Razorpay live flag)

Auth:     Same secrets as pmax_campaign_setup.py
Account:  1137623123
Campaign: LXGNDRY (resolved by name)

Usage:
  python pmax_report.py                  # last 14 days
  python pmax_report.py --days 7         # last 7 days
  python pmax_report.py --days 30        # last 30 days
  python pmax_report.py --campaign-id XXXXXXXX  # force specific campaign resource ID

Required env secrets:
  GOOGLE_ADS_DEVELOPER_TOKEN
  GOOGLE_ADS_CLIENT_ID
  GOOGLE_ADS_CLIENT_SECRET
  GOOGLE_ADS_REFRESH_TOKEN
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# ── Config ────────────────────────────────────────────────────────────────────
CUSTOMER_ID   = "1137623123"
CAMPAIGN_NAME = "LXGNDRY"   # partial match — resolves to the live campaign
DEFAULT_DAYS  = 14

# ── Client ────────────────────────────────────────────────────────────────────
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

# ── Helpers ───────────────────────────────────────────────────────────────────
def date_range(days: int):
    end   = datetime.today()
    start = end - timedelta(days=days - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def micros_to_dollars(micros: int) -> float:
    return micros / 1_000_000

def safe_ctr(clicks, impressions):
    return (clicks / impressions * 100) if impressions else 0.0

def safe_cpc(cost_micros, clicks):
    return micros_to_dollars(cost_micros) / clicks if clicks else 0.0

def section(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)

def row(label, value, width=28):
    print(f"  {label:<{width}} {value}")

# ── 1. Resolve Campaign ───────────────────────────────────────────────────────
def resolve_campaign(client, campaign_id_override=None):
    """
    Returns (campaign_resource_name, campaign_id, campaign_name, status, bidding_type).
    If campaign_id_override is set, resolves by ID; otherwise searches by name CONTAINS LXGNDRY.
    """
    ga_service = client.get_service("GoogleAdsService")

    if campaign_id_override:
        where = f"campaign.id = {campaign_id_override}"
    else:
        where = f"campaign.name LIKE '%{CAMPAIGN_NAME}%'"

    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          campaign.bidding_strategy_type,
          campaign.resource_name
        FROM campaign
        WHERE {where}
        LIMIT 10
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    campaigns = list(response)

    if not campaigns:
        print(f"  ERROR: No campaign found matching '{CAMPAIGN_NAME}'. Check the name or pass --campaign-id.")
        sys.exit(1)

    if len(campaigns) > 1:
        print(f"  WARNING: Multiple campaigns matched. Using first result.")

    c = campaigns[0].campaign
    return c.resource_name, str(c.id), c.name, c.status.name, c.bidding_strategy_type.name

# ── 2. Campaign-Level Daily Metrics ──────────────────────────────────────────
def get_daily_metrics(client, campaign_resource: str, start_date: str, end_date: str):
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          segments.date,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.conversions_value,
          metrics.all_conversions,
          metrics.all_conversions_value
        FROM campaign
        WHERE campaign.resource_name = '{campaign_resource}'
          AND segments.date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY segments.date ASC
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    rows = []
    for r in response:
        m = r.metrics
        d = r.segments.date
        clicks      = m.clicks
        impressions = m.impressions
        cost_micros = m.cost_micros
        rows.append({
            "date":        d,
            "impressions": impressions,
            "clicks":      clicks,
            "ctr":         safe_ctr(clicks, impressions),
            "cpc":         safe_cpc(cost_micros, clicks),
            "spend":       micros_to_dollars(cost_micros),
            "conversions": m.conversions,
            "conv_value":  m.conversions_value,
            "all_conv":    m.all_conversions,
        })
    return rows

# ── 3. Asset Group Metrics ────────────────────────────────────────────────────
def get_asset_group_metrics(client, campaign_resource: str, start_date: str, end_date: str):
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          asset_group.name,
          asset_group.status,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.all_conversions
        FROM asset_group
        WHERE campaign.resource_name = '{campaign_resource}'
          AND segments.date BETWEEN '{start_date}' AND '{end_date}'
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    groups = {}
    for r in response:
        name   = r.asset_group.name
        status = r.asset_group.status.name
        m      = r.metrics
        if name not in groups:
            groups[name] = {
                "status":      status,
                "impressions": 0,
                "clicks":      0,
                "cost_micros": 0,
                "conversions": 0.0,
                "all_conv":    0.0,
            }
        groups[name]["impressions"] += m.impressions
        groups[name]["clicks"]      += m.clicks
        groups[name]["cost_micros"] += m.cost_micros
        groups[name]["conversions"] += m.conversions
        groups[name]["all_conv"]    += m.all_conversions
    return groups

# ── 4. Search Theme Performance ───────────────────────────────────────────────
def get_search_term_insights(client, campaign_resource: str, start_date: str, end_date: str):
    """
    Returns top search categories driving traffic (PMax search term insight).
    Falls back gracefully if the account doesn't have access.
    """
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          campaign_search_term_insight.category_label,
          metrics.clicks,
          metrics.impressions,
          metrics.cost_micros,
          metrics.conversions
        FROM campaign_search_term_insight
        WHERE campaign.resource_name = '{campaign_resource}'
          AND segments.date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY metrics.clicks DESC
        LIMIT 20
    """
    try:
        response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
        results = []
        for r in response:
            m = r.metrics
            results.append({
                "category":    r.campaign_search_term_insight.category_label,
                "clicks":      m.clicks,
                "impressions": m.impressions,
                "spend":       micros_to_dollars(m.cost_micros),
                "conversions": m.conversions,
            })
        return results
    except GoogleAdsException:
        return []

# ── 5. Print Report ───────────────────────────────────────────────────────────
def print_report(camp_meta, daily_rows, asset_groups, search_insights, days):
    camp_rname, camp_id, camp_name, status, bidding = camp_meta

    now = datetime.now().strftime("%Y-%m-%d %H:%M CDT")

    section(f"LXGNDRY CAMPAIGN PERFORMANCE REPORT")
    row("Generated",     now)
    row("Campaign",      camp_name)
    row("Campaign ID",   camp_id)
    row("Status",        status)
    row("Bidding",       bidding)
    row("Window",        f"Last {days} days")

    # ── Totals ────────────────────────────────────────────────────────────────
    total_impressions = sum(r["impressions"] for r in daily_rows)
    total_clicks      = sum(r["clicks"]      for r in daily_rows)
    total_spend       = sum(r["spend"]       for r in daily_rows)
    total_conv        = sum(r["conversions"] for r in daily_rows)
    total_all_conv    = sum(r["all_conv"]    for r in daily_rows)
    total_conv_value  = sum(r["conv_value"]  for r in daily_rows)
    avg_ctr           = safe_ctr(total_clicks, total_impressions)
    avg_cpc           = safe_cpc(int(total_spend * 1_000_000), total_clicks)

    section("CAMPAIGN TOTALS")
    row("Impressions",   f"{total_impressions:,}")
    row("Clicks",        f"{total_clicks:,}")
    row("Avg CTR",       f"{avg_ctr:.2f}%")
    row("Avg CPC",       f"${avg_cpc:.4f}")
    row("Total Spend",   f"${total_spend:.2f}")
    row("Conversions",   f"{total_conv:.1f}  (all conv: {total_all_conv:.0f})")
    row("Conv. Value",   f"${total_conv_value:.2f}")
    if total_conv > 0:
        row("Cost / Conv",   f"${total_spend / total_conv:.2f}")
        row("ROAS",          f"{(total_conv_value / total_spend):.2f}x" if total_spend > 0 else "N/A")

    # ── Daily Breakdown ───────────────────────────────────────────────────────
    section("DAILY BREAKDOWN")
    header = f"  {'Date':<12} {'Impr':>8} {'Clicks':>7} {'CTR':>6} {'CPC':>7} {'Spend':>8} {'Conv':>6} {'AllConv':>8}"
    print(header)
    print("  " + "-" * 68)
    for r in daily_rows:
        print(
            f"  {r['date']:<12} "
            f"{r['impressions']:>8,} "
            f"{r['clicks']:>7,} "
            f"{r['ctr']:>5.1f}% "
            f"${r['cpc']:>6.4f} "
            f"${r['spend']:>7.2f} "
            f"{r['conversions']:>6.1f} "
            f"{r['all_conv']:>8.0f}"
        )

    # ── Asset Group Breakdown ─────────────────────────────────────────────────
    if asset_groups:
        section("ASSET GROUP BREAKDOWN")
        header = f"  {'Asset Group':<35} {'Status':<10} {'Impr':>8} {'Clicks':>7} {'Spend':>8} {'Conv':>6}"
        print(header)
        print("  " + "-" * 78)
        for name, ag in sorted(asset_groups.items(), key=lambda x: -x[1]["impressions"]):
            ag_clicks = ag["clicks"]
            ag_impr   = ag["impressions"]
            ag_spend  = micros_to_dollars(ag["cost_micros"])
            print(
                f"  {name[:34]:<35} "
                f"{ag['status']:<10} "
                f"{ag_impr:>8,} "
                f"{ag_clicks:>7,} "
                f"${ag_spend:>7.2f} "
                f"{ag['conversions']:>6.1f}"
            )

    # ── Search Term Insights ──────────────────────────────────────────────────
    if search_insights:
        section("TOP SEARCH CATEGORIES (PMax Insights)")
        header = f"  {'Category':<40} {'Clicks':>7} {'Impr':>8} {'Spend':>8} {'Conv':>6}"
        print(header)
        print("  " + "-" * 70)
        for s in search_insights[:15]:
            print(
                f"  {s['category'][:39]:<40} "
                f"{s['clicks']:>7,} "
                f"{s['impressions']:>8,} "
                f"${s['spend']:>7.2f} "
                f"{s['conversions']:>6.1f}"
            )
    else:
        section("SEARCH INSIGHTS")
        print("  Search term insights not available for this account tier.")
        print("  Use Google Ads UI → Insights tab for category-level data.")

    # ── Verdict ───────────────────────────────────────────────────────────────
    section("ASSESSMENT")
    if not daily_rows:
        print("  No data returned for the selected date range.")
    else:
        zero_conv_days = sum(1 for r in daily_rows if r["conversions"] == 0)
        high_ctr_days  = sum(1 for r in daily_rows if r["ctr"] > 5.0)
        top_day        = max(daily_rows, key=lambda r: r["clicks"])
        low_day        = min(daily_rows, key=lambda r: r["clicks"])

        print(f"  Top click day   : {top_day['date']} ({top_day['clicks']:,} clicks, CTR {top_day['ctr']:.1f}%)")
        print(f"  Lowest day      : {low_day['date']} ({low_day['clicks']:,} clicks)")
        print(f"  Days with CTR>5%: {high_ctr_days} of {len(daily_rows)}")
        print(f"  Zero conv days  : {zero_conv_days} of {len(daily_rows)}")
        print()

        if total_conv == 0 and total_all_conv > 100:
            print("  ⚠  No hard conversions recorded but high all-conversions signal.")
            print("     Check conversion action setup — likely micro-conversions only.")
        elif total_conv == 0:
            print("  ⚠  Zero conversions recorded. Review payment gateway and checkout.")
            print("     Razorpay was activated Jun 23 — monitor for 48-72h post-activation.")
        else:
            roas = total_conv_value / total_spend if total_spend > 0 else 0
            print(f"  ✅ {total_conv:.0f} conversions recorded. ROAS: {roas:.2f}x")

        if avg_cpc < 0.01:
            print("  ✅ CPC sub-penny — algorithm has found efficient audience.")
        elif avg_cpc < 0.05:
            print("  ✅ CPC under $0.05 — learning phase still efficient.")
        else:
            print(f"  ⚠  CPC ${avg_cpc:.4f} — elevated, check if learning completed.")

        if status != "ENABLED":
            print(f"\n  ❌ Campaign is NOT ENABLED (status: {status}). No traffic will serve.")

    print()
    print("=" * 70)
    print("  END OF REPORT")
    print("=" * 70)
    print()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="LXGNDRY PMax Performance Report")
    parser.add_argument("--days",        type=int, default=DEFAULT_DAYS, help="Number of days to look back (default: 14)")
    parser.add_argument("--campaign-id", type=str, default=None,         help="Override campaign ID (optional)")
    args = parser.parse_args()

    start_date, end_date = date_range(args.days)

    print()
    print("  Connecting to Google Ads API...")
    client = get_client()

    print(f"  Resolving campaign '{CAMPAIGN_NAME}'...")
    camp_meta = resolve_campaign(client, args.campaign_id)
    camp_rname = camp_meta[0]
    print(f"  Found: {camp_meta[2]} (ID: {camp_meta[1]}, Status: {camp_meta[3]})")

    print(f"  Pulling daily metrics ({start_date} → {end_date})...")
    daily_rows = get_daily_metrics(client, camp_rname, start_date, end_date)

    print(f"  Pulling asset group metrics...")
    asset_groups = get_asset_group_metrics(client, camp_rname, start_date, end_date)

    print(f"  Pulling search term insights...")
    search_insights = get_search_term_insights(client, camp_rname, start_date, end_date)

    print_report(camp_meta, daily_rows, asset_groups, search_insights, args.days)


if __name__ == "__main__":
    main()
