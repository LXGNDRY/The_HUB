"""
Analytics router — Google Analytics 4 (Data API) integration.
Prefix in main.py: /api/analytics
"""

import os
import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger("gcp-bot.analytics")
router = APIRouter()

GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "")


def _ga4_client():
    """Build an authenticated GA4 Data API client."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from auth.credentials import get_credentials
    return BetaAnalyticsDataClient(credentials=get_credentials())


@router.get("/traffic", summary="GA4 traffic overview")
def traffic_overview(days: int = 28):
    """
    Returns sessions, users, bounce rate, and avg session duration
    from GA4 for legendary-branding.com over the last `days` days.
    """
    try:
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest,
        )

        prop = GA4_PROPERTY_ID or os.getenv("GA4_PROPERTY_ID", "")
        if not prop:
            raise ValueError("GA4_PROPERTY_ID env var not set")

        client = _ga4_client()
        request = RunReportRequest(
            property=f"properties/{prop}",
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
                "date": row.dimension_values[0].value,
                "sessions": int(row.metric_values[0].value),
                "users": int(row.metric_values[1].value),
                "bounce_rate": round(float(row.metric_values[2].value) * 100, 2),
                "avg_session_duration_s": round(float(row.metric_values[3].value), 1),
            }
            for row in response.rows
        ]
        return {"period_days": days, "rows": rows}
    except Exception as exc:
        logger.error("GA4 traffic error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/top-pages", summary="GA4 top pages by sessions")
def top_pages(days: int = 28, limit: int = 20):
    """
    Returns the top pages ranked by sessions over the last `days` days.
    """
    try:
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest, OrderBy,
        )

        prop = GA4_PROPERTY_ID or os.getenv("GA4_PROPERTY_ID", "")
        if not prop:
            raise ValueError("GA4_PROPERTY_ID env var not set")

        client = _ga4_client()
        request = RunReportRequest(
            property=f"properties/{prop}",
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
            dimensions=[Dimension(name="pagePath")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="screenPageViews"),
                Metric(name="bounceRate"),
            ],
            order_bys=[
                OrderBy(
                    metric=OrderBy.MetricOrderBy(metric_name="sessions"),
                    desc=True,
                )
            ],
            limit=limit,
        )
        response = client.run_report(request)
        rows = [
            {
                "page": row.dimension_values[0].value,
                "sessions": int(row.metric_values[0].value),
                "pageviews": int(row.metric_values[1].value),
                "bounce_rate": round(float(row.metric_values[2].value) * 100, 2),
            }
            for row in response.rows
        ]
        return {"period_days": days, "top_pages": rows}
    except Exception as exc:
        logger.error("GA4 top-pages error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
