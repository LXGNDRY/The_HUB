#!/usr/bin/env python3
"""
ga4_bot_traffic_audit.py — Legendary Branding

Diagnoses where "begin_checkout" traffic is actually coming from, to separate
real shoppers from bots/spam/invalid clicks. GA4 already auto-filters known
bots (IAB/ABC list) at collection time, so a session that reaches GA4 and
fires begin_checkout is not a classic crawler — if there's a huge gap between
begin_checkout and purchase, the more likely causes surfaced here are:
  - Referral/spam traffic (ghost sessions with no real page interaction)
  - Invalid/low-quality ad clicks (a single source/medium dominating
    begin_checkout with near-zero purchases and near-zero session duration)
  - A mis-firing pixel (same event repeated for a tiny set of sessions/pages)

Sections:
  A. begin_checkout volume by source/medium, with session duration + bounce
     rate + eventual purchases for the SAME segment (the tell: high volume +
     near-0 duration + near-0 purchases = low-quality/invalid traffic)
  B. begin_checkout volume by device category + browser (old/unusual browser
     strings are the closest GA4 proxy for residual bot-like traffic)
  C. begin_checkout volume by country (mismatched-to-market countries at
     high volume is a common invalid-traffic signal)
  D. begin_checkout volume by landing page (concentration on one page/URL
     param pattern suggests automated/scripted hits, not organic browsing)
  E. Assessment — auto-generated flags for the segments that look suspicious

Auth (GA4):
  GA4_TOKEN_JSON  — JSON string of an authorized user credential (preferred)
  GA4_PROPERTY_ID — numeric GA4 property ID

Usage:
  python scripts/ga4_bot_traffic_audit.py
  python scripts/ga4_bot_traffic_audit.py --days 30
"""

import os
import sys
import json
import argparse
from datetime import datetime

EVENT_NAME = "ga4_begin_checkout"
PURCHASE_EVENT = "ga4_purchase"

# A segment is flagged as suspicious if it clears the volume floor AND
# matches at least one of: near-zero session duration, near-zero purchases
# relative to its share of begin_checkout volume.
MIN_SESSIONS_TO_FLAG = 10
LOW_DURATION_S = 3.0
LOW_PURCHASE_SHARE_RATIO = 0.15  # purchase share should be at least 15% of begin_checkout share


def section(title: str):
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def row(label, value, width=32):
    print(f"  {label:<{width}} {value}")


def get_ga4_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    token_json = os.getenv("GA4_TOKEN_JSON", "")
    if token_json:
        from google.oauth2.credentials import Credentials
        info = json.loads(token_json)
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


def run_breakdown(ga4, property_id: str, days: int, dimension_name: str):
    """
    For a given dimension, return per-segment: begin_checkout event count,
    purchase event count, sessions, avg session duration, bounce rate.
    Two report calls: one for the funnel events (eventName filter), one for
    session-quality metrics scoped to sessions containing the dimension.
    """
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest, FilterExpression,
        Filter, FilterExpressionList, OrderBy,
    )

    date_range = [DateRange(start_date=f"{days}daysAgo", end_date="today")]

    # Funnel event counts per segment
    event_request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=date_range,
        dimensions=[Dimension(name=dimension_name), Dimension(name="eventName")],
        metrics=[Metric(name="eventCount")],
        dimension_filter=FilterExpression(
            or_group=FilterExpressionList(
                expressions=[
                    FilterExpression(filter=Filter(
                        field_name="eventName",
                        string_filter=Filter.StringFilter(value=EVENT_NAME),
                    )),
                    FilterExpression(filter=Filter(
                        field_name="eventName",
                        string_filter=Filter.StringFilter(value=PURCHASE_EVENT),
                    )),
                ]
            )
        ),
        limit=100,
    )
    event_resp = ga4.run_report(event_request)

    segments = {}
    for r in event_resp.rows:
        seg = r.dimension_values[0].value
        evt = r.dimension_values[1].value
        count = int(r.metric_values[0].value)
        segments.setdefault(seg, {"begin_checkout": 0, "purchase": 0, "sessions": 0, "avg_duration": 0.0, "bounce_rate": 0.0})
        if evt == EVENT_NAME:
            segments[seg]["begin_checkout"] += count
        elif evt == PURCHASE_EVENT:
            segments[seg]["purchase"] += count

    # Session-quality metrics per segment (all sessions, not filtered to the funnel event)
    quality_request = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=date_range,
        dimensions=[Dimension(name=dimension_name)],
        metrics=[
            Metric(name="sessions"),
            Metric(name="averageSessionDuration"),
            Metric(name="bounceRate"),
        ],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=100,
    )
    quality_resp = ga4.run_report(quality_request)
    for r in quality_resp.rows:
        seg = r.dimension_values[0].value
        if seg not in segments:
            continue
        segments[seg]["sessions"] = int(r.metric_values[0].value)
        segments[seg]["avg_duration"] = round(float(r.metric_values[1].value), 1)
        segments[seg]["bounce_rate"] = round(float(r.metric_values[2].value) * 100, 1)

    return segments


def print_breakdown(title: str, segments: dict, total_begin: int, total_purchase: int):
    section(title)
    if not segments:
        print("  No data returned for this dimension.")
        return []

    header = f"  {'Segment':<38} {'Begin CO':>9} {'Purch':>6} {'Sessions':>9} {'AvgDur(s)':>10} {'Bounce%':>8}"
    print(header)
    print("  " + "-" * 84)

    flagged = []
    rows = sorted(segments.items(), key=lambda kv: -kv[1]["begin_checkout"])
    for seg, d in rows:
        if d["begin_checkout"] == 0:
            continue
        print(
            f"  {seg[:37]:<38} "
            f"{d['begin_checkout']:>9,} "
            f"{d['purchase']:>6,} "
            f"{d['sessions']:>9,} "
            f"{d['avg_duration']:>10.1f} "
            f"{d['bounce_rate']:>7.1f}%"
        )

        # Suspicion heuristic
        if d["sessions"] < MIN_SESSIONS_TO_FLAG:
            continue
        begin_share = d["begin_checkout"] / total_begin if total_begin else 0
        purch_share = d["purchase"] / total_purchase if total_purchase else 0
        low_duration = d["avg_duration"] < LOW_DURATION_S
        low_purch_share = begin_share > 0 and (purch_share / begin_share if begin_share else 0) < LOW_PURCHASE_SHARE_RATIO
        if low_duration or low_purch_share:
            reasons = []
            if low_duration:
                reasons.append(f"avg session duration {d['avg_duration']:.1f}s")
            if low_purch_share:
                reasons.append(f"{begin_share*100:.0f}% of begin_checkout volume but only {purch_share*100:.0f}% of purchases")
            flagged.append((seg, reasons))
    return flagged


def main():
    parser = argparse.ArgumentParser(description="GA4 begin_checkout traffic quality audit")
    parser.add_argument("--days", type=int, default=30, help="Days to look back (default: 30)")
    args = parser.parse_args()

    property_id = os.getenv("GA4_PROPERTY_ID", "")
    if not property_id:
        print("ERROR: GA4_PROPERTY_ID not set.", file=sys.stderr)
        sys.exit(1)

    print(f"\n  Connecting to GA4 Data API (property {property_id})...")
    ga4 = get_ga4_client()

    now = datetime.now().strftime("%Y-%m-%d %H:%M CDT")
    section("GA4 CHECKOUT TRAFFIC QUALITY AUDIT — LEGENDARY BRANDING")
    row("Generated", now)
    row("Period", f"Last {args.days} days")

    dimensions = [
        ("A. BY SOURCE / MEDIUM", "sessionSourceMedium"),
        ("B. BY DEVICE CATEGORY", "deviceCategory"),
        ("C. BY BROWSER", "browser"),
        ("D. BY COUNTRY", "country"),
        ("E. BY LANDING PAGE", "landingPagePlusQueryString"),
    ]

    all_flags = []
    total_begin = total_purchase = None

    for title, dim in dimensions:
        print(f"  Fetching breakdown by {dim}...")
        segs = run_breakdown(ga4, property_id, args.days, dim)
        if total_begin is None:
            total_begin = sum(d["begin_checkout"] for d in segs.values())
            total_purchase = sum(d["purchase"] for d in segs.values())
        flagged = print_breakdown(title, segs, total_begin, total_purchase)
        all_flags.append((title, flagged))

    section("F. ASSESSMENT")
    row("Total begin_checkout events", f"{total_begin:,}")
    row("Total purchase events", f"{total_purchase:,}")
    overall_cr = (total_purchase / total_begin * 100) if total_begin else 0.0
    row("Overall checkout→purchase rate", f"{overall_cr:.2f}%")
    print()

    any_flagged = False
    for title, flagged in all_flags:
        if not flagged:
            continue
        any_flagged = True
        print(f"  {title}:")
        for seg, reasons in flagged:
            print(f"    ⚠  {seg}: {'; '.join(reasons)}")
        print()

    if not any_flagged:
        print("  No segment cleared the suspicion thresholds (min "
              f"{MIN_SESSIONS_TO_FLAG} sessions, <{LOW_DURATION_S}s avg duration, "
              f"or purchase share < {LOW_PURCHASE_SHARE_RATIO*100:.0f}% of begin_checkout share).")
        print("  If checkout→purchase rate is still low overall, the drop-off is likely")
        print("  a genuine funnel/UX/payment issue rather than bot or spam traffic —")
        print("  see google_ads_checkout_audit.py Section E/F/G for step-by-step drop-off.")

    print()
    print("=" * 78)
    print("  END OF REPORT")
    print("=" * 78)
    print()


if __name__ == "__main__":
    main()
