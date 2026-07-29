#!/usr/bin/env python3
"""
google_ads_checkout_audit.py — Legendary Branding
Full audit of all running Google Ads campaigns + GA4 checkout funnel drop-off analysis.

Sections:
  A. Google Ads — all campaigns: status, budget, spend, conversions, ROAS
  B. Conversion actions configured in the account
  C. Performance Max — asset group breakdown
  D. Search term insights (PMax)
  E. GA4 checkout funnel — overall step-by-step drop-off
  F. GA4 checkout funnel — by device (mobile vs desktop)
  G. Assessment — auto-generated observations

Auth (Google Ads):
  GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_CLIENT_ID,
  GOOGLE_ADS_CLIENT_SECRET, GOOGLE_ADS_REFRESH_TOKEN

Auth (GA4):
  GA4_TOKEN_JSON  — JSON string of an authorized user credential (preferred)
  GA4_PROPERTY_ID — numeric GA4 property ID

Usage:
  python scripts/google_ads_checkout_audit.py
  python scripts/google_ads_checkout_audit.py --days 14
  python scripts/google_ads_checkout_audit.py --days 90
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# ── Config ─────────────────────────────────────────────────────────────────────
CUSTOMER_ID  = "1137623123"
DEFAULT_DAYS = 30

FUNNEL_EVENTS = [
    "ga4_begin_checkout",
    "ga4_add_shipping_info",
    "ga4_add_payment_info",
    "ga4_purchase",
]

FUNNEL_LABELS = {
    "ga4_begin_checkout":    "1. Begin Checkout",
    "ga4_add_shipping_info": "2. Shipping Info",
    "ga4_add_payment_info":  "3. Payment Info",
    "ga4_purchase":          "4. Purchase",
}

# ── Shared helpers ─────────────────────────────────────────────────────────────

def date_range(days: int):
    end   = datetime.today()
    start = end - timedelta(days=days - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def micros_to_dollars(micros: int) -> float:
    return micros / 1_000_000


def safe_div(numerator, denominator, pct=False):
    if not denominator:
        return 0.0
    v = numerator / denominator
    return v * 100 if pct else v


def section(title: str):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def row(label, value, width=32):
    print(f"  {label:<{width}} {value}")


def drop_pct(a, b):
    """Percentage of visitors who dropped between step a and step b."""
    if not a:
        return 0.0
    return (1 - b / a) * 100


# ── Part A — Google Ads client + campaign data ─────────────────────────────────

def get_ads_client():
    config = {
        "developer_token":   os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id":         os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret":     os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token":     os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": CUSTOMER_ID,
        "use_proto_plus":    True,
    }
    return GoogleAdsClient.load_from_dict(config)


def get_all_campaigns(client):
    """Return all campaigns with budget and status info."""
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          campaign.serving_status,
          campaign.advertising_channel_type,
          campaign.bidding_strategy_type,
          campaign_budget.amount_micros,
          campaign_budget.delivery_method
        FROM campaign
        ORDER BY campaign.name ASC
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    campaigns = []
    for r in response:
        c = r.campaign
        b = r.campaign_budget
        campaigns.append({
            "id":            str(c.id),
            "name":          c.name,
            "status":        c.status.name,
            "serving":       c.serving_status.name,
            "type":          c.advertising_channel_type.name,
            "bidding":       c.bidding_strategy_type.name,
            "budget_day":    micros_to_dollars(b.amount_micros),
            "resource_name": c.resource_name,
        })
    return campaigns


def get_all_campaign_metrics(client, start_date: str, end_date: str):
    """Return campaign-level metrics rolled up over the date range."""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.conversions_value,
          metrics.all_conversions
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    metrics = {}
    for r in response:
        cid = str(r.campaign.id)
        m   = r.metrics
        if cid not in metrics:
            metrics[cid] = {
                "name":        r.campaign.name,
                "impressions": 0,
                "clicks":      0,
                "cost_micros": 0,
                "conversions": 0.0,
                "conv_value":  0.0,
                "all_conv":    0.0,
            }
        metrics[cid]["impressions"] += m.impressions
        metrics[cid]["clicks"]      += m.clicks
        metrics[cid]["cost_micros"] += m.cost_micros
        metrics[cid]["conversions"] += m.conversions
        metrics[cid]["conv_value"]  += m.conversions_value
        metrics[cid]["all_conv"]    += m.all_conversions
    return metrics


def get_conversion_actions(client):
    """List all conversion actions configured in the account."""
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT
          conversion_action.id,
          conversion_action.name,
          conversion_action.status,
          conversion_action.category,
          conversion_action.type,
          conversion_action.include_in_conversions_metric,
          conversion_action.counting_type
        FROM conversion_action
        ORDER BY conversion_action.name ASC
    """
    response = ga_service.search(customer_id=CUSTOMER_ID, query=query)
    actions = []
    for r in response:
        ca = r.conversion_action
        actions.append({
            "id":          str(ca.id),
            "name":        ca.name,
            "status":      ca.status.name,
            "category":    ca.category.name,
            "type":        ca.type_.name,
            "primary":     ca.include_in_conversions_metric,
            "counting":    ca.counting_type.name,
        })
    return actions


def get_asset_group_metrics(client, campaign_resource: str, start_date: str, end_date: str):
    """Asset group metrics for a PMax campaign."""
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


def get_search_term_insights(client, campaign_resource: str, start_date: str, end_date: str):
    """PMax search term insight categories."""
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


# ── Part B — GA4 client + funnel data ─────────────────────────────────────────

def get_ga4_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    token_json = os.getenv("GA4_TOKEN_JSON", "")
    if token_json:
        from google.oauth2.credentials import Credentials
        info  = json.loads(token_json)
        creds = Credentials(
            token=info.get("access_token"),
            refresh_token=info.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=info.get("client_id"),
            client_secret=info.get("client_secret"),
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )
    else:
        from google.auth import default
        creds, _ = default(scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    return BetaAnalyticsDataClient(credentials=creds)


def get_funnel_counts(ga4, property_id: str, days: int) -> dict:
    """Return event counts for each checkout funnel step."""
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest, FilterExpression,
        Filter, FilterExpressionList,
    )
    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        dimensions=[Dimension(name="eventName")],
        metrics=[Metric(name="eventCount")],
        dimension_filter=FilterExpression(
            or_group=FilterExpressionList(
                expressions=[
                    FilterExpression(
                        filter=Filter(
                            field_name="eventName",
                            string_filter=Filter.StringFilter(value=evt),
                        )
                    )
                    for evt in FUNNEL_EVENTS
                ]
            )
        ),
    )
    response = ga4.run_report(request)
    counts = {evt: 0 for evt in FUNNEL_EVENTS}
    for r in response.rows:
        name  = r.dimension_values[0].value
        count = int(r.metric_values[0].value)
        if name in counts:
            counts[name] = count
    return counts


def get_funnel_by_device(ga4, property_id: str, days: int) -> dict:
    """Return funnel step counts broken out by device category."""
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest, FilterExpression,
        Filter, FilterExpressionList,
    )
    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        dimensions=[
            Dimension(name="deviceCategory"),
            Dimension(name="eventName"),
        ],
        metrics=[Metric(name="eventCount")],
        dimension_filter=FilterExpression(
            or_group=FilterExpressionList(
                expressions=[
                    FilterExpression(
                        filter=Filter(
                            field_name="eventName",
                            string_filter=Filter.StringFilter(value=evt),
                        )
                    )
                    for evt in FUNNEL_EVENTS
                ]
            )
        ),
    )
    response = ga4.run_report(request)
    by_device = {}
    for r in response.rows:
        device = r.dimension_values[0].value
        evt    = r.dimension_values[1].value
        count  = int(r.metric_values[0].value)
        if device not in by_device:
            by_device[device] = {e: 0 for e in FUNNEL_EVENTS}
        if evt in by_device[device]:
            by_device[device][evt] = count
    return by_device


def get_checkout_sources(ga4, property_id: str, days: int) -> list:
    """Top session source/mediums for sessions that began checkout."""
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest, FilterExpression,
        Filter, OrderBy,
    )
    request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        dimensions=[Dimension(name="sessionSourceMedium")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="eventCount"),
        ],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="eventName",
                string_filter=Filter.StringFilter(value="ga4_begin_checkout"),
            )
        ),
        order_bys=[OrderBy(
            metric=OrderBy.MetricOrderBy(metric_name="sessions"),
            desc=True,
        )],
        limit=15,
    )
    try:
        response = ga4.run_report(request)
        sources = []
        for r in response.rows:
            sources.append({
                "source":   r.dimension_values[0].value,
                "sessions": int(r.metric_values[0].value),
                "checkouts": int(r.metric_values[1].value),
            })
        return sources
    except Exception:
        return []


# ── Part C — Print report ──────────────────────────────────────────────────────

def print_funnel_table(counts: dict, label_prefix=""):
    events  = FUNNEL_EVENTS
    section_counts = [counts.get(e, 0) for e in events]
    top = section_counts[0] if section_counts[0] else 1

    print(f"  {'Step':<30} {'Count':>8}  {'Of Start':>9}  {'Step Drop':>10}")
    print("  " + "-" * 62)
    for i, evt in enumerate(events):
        cnt       = section_counts[i]
        pct_start = safe_div(cnt, top, pct=True)
        step_drop = drop_pct(section_counts[i - 1] if i > 0 else cnt, cnt) if i > 0 else 0.0
        drop_str  = f"-{step_drop:.1f}%" if i > 0 else "—"
        print(f"  {FUNNEL_LABELS[evt]:<30} {cnt:>8,}  {pct_start:>8.1f}%  {drop_str:>10}")


def print_report(
    campaigns, camp_metrics, conv_actions, asset_groups_by_camp,
    search_insights_by_camp, funnel_counts, funnel_by_device,
    checkout_sources, days, start_date, end_date
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M CDT")

    section("GOOGLE ADS + CHECKOUT AUDIT — LEGENDARY BRANDING")
    row("Generated",   now)
    row("Period",      f"Last {days} days  ({start_date} → {end_date})")
    row("Customer ID", CUSTOMER_ID)

    # ── A. Campaign overview ──────────────────────────────────────────────────
    section("A. ALL CAMPAIGNS — OVERVIEW")
    header = f"  {'Campaign':<38} {'Type':<8} {'Status':<10} {'Budget/Day':>10} {'Spend':>9} {'Conv':>7} {'ROAS':>7}"
    print(header)
    print("  " + "-" * 92)

    total_spend = total_conv = total_conv_val = 0.0
    for c in campaigns:
        cid    = c["id"]
        m      = camp_metrics.get(cid, {})
        spend  = micros_to_dollars(m.get("cost_micros", 0))
        conv   = m.get("conversions", 0.0)
        cval   = m.get("conv_value", 0.0)
        roas   = safe_div(cval, spend)
        status = c["status"]
        flag   = "✅" if status == "ENABLED" else "⚠ "
        total_spend   += spend
        total_conv    += conv
        total_conv_val += cval
        roas_str = f"{roas:.2f}x" if spend > 0 and conv > 0 else "—"
        print(
            f"  {flag} {c['name'][:36]:<36} "
            f"{c['type'][:7]:<8} "
            f"{status[:9]:<10} "
            f"${c['budget_day']:>9.2f} "
            f"${spend:>8.2f} "
            f"{conv:>7.1f} "
            f"{roas_str:>7}"
        )
    print()
    overall_roas = safe_div(total_conv_val, total_spend)
    row("TOTAL SPEND",      f"${total_spend:.2f}")
    row("TOTAL CONVERSIONS", f"{total_conv:.1f}")
    row("TOTAL CONV VALUE",  f"${total_conv_val:.2f}")
    row("ACCOUNT ROAS",      f"{overall_roas:.2f}x" if total_spend > 0 else "N/A")

    # ── B. Conversion actions ─────────────────────────────────────────────────
    section("B. CONVERSION ACTIONS CONFIGURED")
    primary   = [a for a in conv_actions if a["primary"]]
    secondary = [a for a in conv_actions if not a["primary"]]

    print("  PRIMARY (count toward 'Conversions' column):")
    if primary:
        for a in primary:
            print(f"    ✅ {a['name']:<45} [{a['category']}]  {a['counting']}")
    else:
        print("    (none)")

    print()
    print("  SECONDARY (count in 'All Conversions' only):")
    if secondary:
        for a in secondary:
            status_icon = "✅" if a["status"] == "ENABLED" else "⚠ "
            print(f"    {status_icon} {a['name']:<45} [{a['category']}]")
    else:
        print("    (none)")

    # ── C. PMax asset groups ──────────────────────────────────────────────────
    section("C. PERFORMANCE MAX — ASSET GROUPS")
    any_pmax = False
    for c in campaigns:
        if c["type"] != "PERFORMANCE_MAX":
            continue
        ag = asset_groups_by_camp.get(c["id"], {})
        if not ag:
            continue
        any_pmax = True
        print(f"\n  Campaign: {c['name']}")
        header = f"    {'Asset Group':<36} {'Status':<10} {'Impr':>8} {'Clicks':>7} {'Spend':>8} {'Conv':>6}"
        print(header)
        print("    " + "-" * 78)
        for name, a in sorted(ag.items(), key=lambda x: -x[1]["impressions"]):
            ag_spend = micros_to_dollars(a["cost_micros"])
            print(
                f"    {name[:35]:<36} "
                f"{a['status']:<10} "
                f"{a['impressions']:>8,} "
                f"{a['clicks']:>7,} "
                f"${ag_spend:>7.2f} "
                f"{a['conversions']:>6.1f}"
            )
    if not any_pmax:
        print("  No Performance Max campaigns found.")

    # ── D. Search term insights ───────────────────────────────────────────────
    section("D. SEARCH TERM INSIGHTS (PMax)")
    any_insights = False
    for c in campaigns:
        if c["type"] != "PERFORMANCE_MAX":
            continue
        insights = search_insights_by_camp.get(c["id"], [])
        if not insights:
            continue
        any_insights = True
        print(f"\n  Campaign: {c['name']}")
        header = f"    {'Category':<42} {'Clicks':>7} {'Impr':>9} {'Spend':>8} {'Conv':>6}"
        print(header)
        print("    " + "-" * 75)
        for s in insights[:15]:
            print(
                f"    {s['category'][:41]:<42} "
                f"{s['clicks']:>7,} "
                f"{s['impressions']:>9,} "
                f"${s['spend']:>7.2f} "
                f"{s['conversions']:>6.1f}"
            )
    if not any_insights:
        print("  Search term insights not available (account tier or no PMax data).")

    # ── E. Checkout funnel — overall ──────────────────────────────────────────
    section("E. CHECKOUT FUNNEL — OVERALL")
    if any(funnel_counts.values()):
        print_funnel_table(funnel_counts)
    else:
        print("  No GA4 checkout funnel data returned for this period.")
        print("  Verify GA4_PROPERTY_ID and that the Web Pixel has been live.")

    # ── F. Checkout funnel — by device ────────────────────────────────────────
    section("F. CHECKOUT FUNNEL — BY DEVICE")
    if funnel_by_device:
        for device in ["mobile", "desktop", "tablet"]:
            counts = funnel_by_device.get(device)
            if not counts or not any(counts.values()):
                continue
            print(f"\n  {device.upper()}")
            print_funnel_table(counts)
    else:
        print("  No device-level GA4 data available.")

    # ── G. Checkout traffic sources ───────────────────────────────────────────
    section("G. TOP TRAFFIC SOURCES INTO CHECKOUT")
    if checkout_sources:
        print(f"  {'Source / Medium':<40} {'Sessions':>9} {'Checkouts':>10}")
        print("  " + "-" * 62)
        for s in checkout_sources:
            print(
                f"  {s['source'][:39]:<40} "
                f"{s['sessions']:>9,} "
                f"{s['checkouts']:>10,}"
            )
    else:
        print("  No traffic source data available.")

    # ── H. Assessment ─────────────────────────────────────────────────────────
    section("H. ASSESSMENT")
    observations = []

    # Ads health
    enabled_camps = [c for c in campaigns if c["status"] == "ENABLED"]
    paused_camps  = [c for c in campaigns if c["status"] != "ENABLED"]
    observations.append(
        f"  Campaigns: {len(enabled_camps)} ENABLED, {len(paused_camps)} not serving"
    )
    if total_spend == 0:
        observations.append("  ⚠  No spend recorded — campaigns may be paused or budgets exhausted.")
    elif total_conv == 0:
        observations.append("  ⚠  Zero primary conversions. Check conversion action setup (Section B).")
    else:
        observations.append(f"  ✅ {total_conv:.0f} primary conversions recorded at ROAS {overall_roas:.2f}x")

    # Primary conversion check
    if not primary:
        observations.append("  ⚠  No conversion actions marked as PRIMARY — Ads bidding has no signal.")
    elif len(primary) > 3:
        observations.append(
            f"  ⚠  {len(primary)} primary conversion actions — too many may dilute bidding signal."
        )

    # Funnel drop-off
    begin  = funnel_counts.get("ga4_begin_checkout", 0)
    ship   = funnel_counts.get("ga4_add_shipping_info", 0)
    pay    = funnel_counts.get("ga4_add_payment_info", 0)
    purch  = funnel_counts.get("ga4_purchase", 0)

    if begin > 0:
        ship_drop  = drop_pct(begin, ship)
        pay_drop   = drop_pct(ship, pay)
        purch_drop = drop_pct(pay, purch)
        overall_cr = safe_div(purch, begin, pct=True)
        observations.append(f"  Checkout conversion rate: {overall_cr:.1f}% ({purch:,} purchases from {begin:,} checkouts)")

        worst = max(
            ("Begin→Shipping", ship_drop),
            ("Shipping→Payment", pay_drop),
            ("Payment→Purchase", purch_drop),
            key=lambda x: x[1]
        )
        observations.append(f"  Biggest drop-off step: {worst[0]} ({worst[1]:.1f}% abandon)")

        if purch_drop > 40:
            observations.append(
                "  ⚠  High Payment→Purchase drop — review Razorpay modal load time, "
                "failed payment UX, and trust signals at payment step."
            )
        if ship_drop > 50:
            observations.append(
                "  ⚠  High Begin→Shipping drop — may indicate unexpected shipping costs "
                "or address form friction."
            )

        # Mobile vs desktop
        mob = funnel_by_device.get("mobile", {})
        dsk = funnel_by_device.get("desktop", {})
        if mob and dsk:
            mob_cr = safe_div(mob.get("ga4_purchase", 0), mob.get("ga4_begin_checkout", 1), pct=True)
            dsk_cr = safe_div(dsk.get("ga4_purchase", 0), dsk.get("ga4_begin_checkout", 1), pct=True)
            observations.append(
                f"  Mobile checkout CR: {mob_cr:.1f}%  |  Desktop checkout CR: {dsk_cr:.1f}%"
            )
            if dsk_cr > 0 and mob_cr < dsk_cr * 0.6:
                observations.append(
                    "  ⚠  Mobile CR significantly below desktop — checkout UX likely needs "
                    "mobile optimization (tap targets, keyboard, Razorpay modal)."
                )
    else:
        observations.append(
            "  ⚠  No GA4 begin_checkout events found — verify the Web Pixel is installed "
            "and GA4_PROPERTY_ID is correct."
        )

    for obs in observations:
        print(obs)

    print()
    print("=" * 72)
    print("  END OF REPORT")
    print("=" * 72)
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Google Ads + Checkout Audit")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help=f"Days to look back (default: {DEFAULT_DAYS})")
    args = parser.parse_args()

    start_date, end_date = date_range(args.days)

    # ── Google Ads ──────────────────────────────────────────────────────────
    print("\n  Connecting to Google Ads API...")
    ads_client = get_ads_client()

    print("  Fetching all campaigns...")
    campaigns = get_all_campaigns(ads_client)
    if not campaigns:
        print("  ERROR: No campaigns found for customer", CUSTOMER_ID)
        sys.exit(1)
    print(f"  Found {len(campaigns)} campaign(s).")

    print(f"  Fetching campaign metrics ({start_date} → {end_date})...")
    camp_metrics = get_all_campaign_metrics(ads_client, start_date, end_date)

    print("  Fetching conversion actions...")
    conv_actions = get_conversion_actions(ads_client)

    pmax_camps = [c for c in campaigns if c["type"] == "PERFORMANCE_MAX"]
    asset_groups_by_camp    = {}
    search_insights_by_camp = {}
    for c in pmax_camps:
        print(f"  Fetching asset groups for: {c['name']}...")
        asset_groups_by_camp[c["id"]] = get_asset_group_metrics(
            ads_client, c["resource_name"], start_date, end_date
        )
        print(f"  Fetching search insights for: {c['name']}...")
        search_insights_by_camp[c["id"]] = get_search_term_insights(
            ads_client, c["resource_name"], start_date, end_date
        )

    # ── GA4 ─────────────────────────────────────────────────────────────────
    property_id = os.getenv("GA4_PROPERTY_ID", "")
    funnel_counts    = {e: 0 for e in FUNNEL_EVENTS}
    funnel_by_device = {}
    checkout_sources = []

    if not property_id:
        print("  WARNING: GA4_PROPERTY_ID not set — skipping funnel analysis.")
    else:
        print("  Connecting to GA4 Data API...")
        try:
            ga4 = get_ga4_client()
            print(f"  Fetching checkout funnel counts (last {args.days} days)...")
            funnel_counts    = get_funnel_counts(ga4, property_id, args.days)
            print("  Fetching funnel by device...")
            funnel_by_device = get_funnel_by_device(ga4, property_id, args.days)
            print("  Fetching checkout traffic sources...")
            checkout_sources = get_checkout_sources(ga4, property_id, args.days)
        except Exception as exc:
            print(f"  WARNING: GA4 query failed — {exc}")
            print("  Skipping funnel sections.")

    print_report(
        campaigns, camp_metrics, conv_actions,
        asset_groups_by_camp, search_insights_by_camp,
        funnel_counts, funnel_by_device, checkout_sources,
        args.days, start_date, end_date,
    )


if __name__ == "__main__":
    main()
