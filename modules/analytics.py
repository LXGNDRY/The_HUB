"""
modules/analytics.py — Google Analytics 4 (Data API) module.

Provides AnalyticsModule used by:
  - scheduler/jobs.py  (sheets_refresh_job — daily dashboard refresh)
  - api/routers/analytics.py  (FastAPI endpoints)

Auth priority:
  1. GA4_TOKEN_JSON env var — JSON string of an authorized user credential
  2. Application Default Credentials with analytics.readonly scope

Property ID is read from GA4_PROPERTY_ID env var.
"""

import os
import json
import logging

logger = logging.getLogger("gcp-bot.analytics")

GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "")


def _build_client():
    """Build a BetaAnalyticsDataClient. Prefers GA4_TOKEN_JSON over ADC."""
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


def _prop(property_id: str = "") -> str:
    pid = property_id or GA4_PROPERTY_ID
    if not pid:
        raise ValueError("GA4_PROPERTY_ID env var is not set")
    return f"properties/{pid}"


class AnalyticsModule:
    """
    Google Analytics 4 Data API wrapper.
    All methods return plain dicts suitable for JSON serialisation or Sheets writes.
    """

    def get_traffic_summary(self, days: int = 28, property_id: str = "") -> dict:
        """
        Daily sessions, users, bounce rate, avg session duration over the period.
        Returns: {period_days, rows: [{date, sessions, users, bounce_rate, avg_session_duration_s}]}
        """
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest,
        )
        client = _build_client()
        request = RunReportRequest(
            property=_prop(property_id),
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            dimensions=[Dimension(name="date")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="totalUsers"),
                Metric(name="bounceRate"),
                Metric(name="averageSessionDuration"),
            ],
        )
        response = client.run_report(request)
        rows = [
            {
                "date": r.dimension_values[0].value,
                "sessions": int(r.metric_values[0].value),
                "users": int(r.metric_values[1].value),
                "bounce_rate": round(float(r.metric_values[2].value) * 100, 2),
                "avg_session_duration_s": round(float(r.metric_values[3].value), 1),
            }
            for r in response.rows
        ]
        total_sessions = sum(r["sessions"] for r in rows)
        total_users = sum(r["users"] for r in rows)
        avg_bounce = round(sum(r["bounce_rate"] for r in rows) / len(rows), 2) if rows else 0
        avg_dur = round(sum(r["avg_session_duration_s"] for r in rows) / len(rows), 1) if rows else 0
        return {
            "period_days": days,
            "date_range": f"Last {days} days",
            "total_sessions": total_sessions,
            "total_users": total_users,
            "bounce_rate": f"{avg_bounce}%",
            "avg_session_duration": avg_dur,
            "rows": rows,
        }

    def get_top_pages(self, days: int = 28, limit: int = 20, property_id: str = "") -> dict:
        """
        Top pages by sessions over the period.
        Returns: {period_days, pages: [{page, sessions, pageviews, bounce_rate}]}
        """
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest, OrderBy,
        )
        client = _build_client()
        request = RunReportRequest(
            property=_prop(property_id),
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            dimensions=[Dimension(name="pagePath")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="screenPageViews"),
                Metric(name="bounceRate"),
            ],
            order_bys=[OrderBy(
                metric=OrderBy.MetricOrderBy(metric_name="sessions"),
                desc=True,
            )],
            limit=limit,
        )
        response = client.run_report(request)
        pages = [
            {
                "page": r.dimension_values[0].value,
                "sessions": int(r.metric_values[0].value),
                "pageviews": int(r.metric_values[1].value),
                "bounce_rate": round(float(r.metric_values[2].value) * 100, 2),
            }
            for r in response.rows
        ]
        return {"period_days": days, "pages": pages}

    def get_country_breakdown(self, days: int = 28, property_id: str = "") -> dict:
        """
        Sessions and conversions (purchases) broken down by country.
        Sorted by sessions descending. Shows where international traffic is coming from.
        Returns: {period_days, countries: [{country, sessions, conversions, conversion_rate_pct}]}
        """
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest, OrderBy,
        )
        client = _build_client()
        request = RunReportRequest(
            property=_prop(property_id),
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            dimensions=[Dimension(name="country")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="conversions"),
            ],
            order_bys=[OrderBy(
                metric=OrderBy.MetricOrderBy(metric_name="sessions"),
                desc=True,
            )],
            limit=50,
        )
        response = client.run_report(request)
        countries = []
        for r in response.rows:
            sessions = int(r.metric_values[0].value)
            conversions = int(r.metric_values[1].value)
            conv_rate = round(conversions / sessions * 100, 2) if sessions > 0 else 0.0
            countries.append({
                "country": r.dimension_values[0].value,
                "sessions": sessions,
                "conversions": conversions,
                "conversion_rate_pct": conv_rate,
            })
        return {"period_days": days, "countries": countries}

    def get_source_medium_breakdown(self, days: int = 28, property_id: str = "") -> dict:
        """
        Sessions and conversions by source / medium (e.g. google / cpc, organic / google).
        Useful for understanding Google Ads vs organic vs direct split.
        Returns: {period_days, sources: [{source_medium, sessions, conversions}]}
        """
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest, OrderBy,
        )
        client = _build_client()
        request = RunReportRequest(
            property=_prop(property_id),
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            dimensions=[Dimension(name="sessionSourceMedium")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="conversions"),
            ],
            order_bys=[OrderBy(
                metric=OrderBy.MetricOrderBy(metric_name="sessions"),
                desc=True,
            )],
            limit=20,
        )
        response = client.run_report(request)
        sources = [
            {
                "source_medium": r.dimension_values[0].value,
                "sessions": int(r.metric_values[0].value),
                "conversions": int(r.metric_values[1].value),
            }
            for r in response.rows
        ]
        return {"period_days": days, "sources": sources}
