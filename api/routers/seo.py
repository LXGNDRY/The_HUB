"""
SEO router — Google Search Console integration.
Prefix in main.py: /api/seo
"""

import os
import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger("gcp-bot.seo")
router = APIRouter()


def _gsc_client():
    """Build an authenticated GSC client via google-api-python-client."""
    from googleapiclient.discovery import build
    from google.auth import default
    creds, _ = default(scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


@router.get("/search-performance", summary="GSC search performance")
def search_performance(
    site_url: str = "https://legendary-branding.com",
    days: int = 28,
):
    """
    Returns clicks, impressions, CTR, and position from Google Search Console
    for the given site over the last `days` days.
    """
    try:
        from datetime import date, timedelta

        service = _gsc_client()
        end = date.today()
        start = end - timedelta(days=days)

        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["query"],
            "rowLimit": 25,
            "startRow": 0,
        }
        resp = (
            service.searchanalytics()
            .query(siteUrl=site_url, body=body)
            .execute()
        )
        rows = resp.get("rows", [])
        return {
            "site": site_url,
            "period_days": days,
            "rows": [
                {
                    "query": r["keys"][0],
                    "clicks": r.get("clicks", 0),
                    "impressions": r.get("impressions", 0),
                    "ctr": round(r.get("ctr", 0) * 100, 2),
                    "position": round(r.get("position", 0), 1),
                }
                for r in rows
            ],
        }
    except Exception as exc:
        logger.error("GSC search-performance error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/crawl-errors", summary="GSC index coverage summary")
def crawl_errors(site_url: str = "https://legendary-branding.com"):
    """
    Returns index coverage / URL status summary using the Search Console
    searchanalytics API (urlcrawlerrorscounts was deprecated in v1).
    Queries the last 7 days grouped by page to surface not-indexed URLs.
    """
    try:
        from datetime import date, timedelta

        service = _gsc_client()
        end = date.today()
        start = end - timedelta(days=7)

        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["page"],
            "rowLimit": 50,
            "dataState": "all",
        }
        resp = (
            service.searchanalytics()
            .query(siteUrl=site_url, body=body)
            .execute()
        )
        rows = resp.get("rows", [])
        return {
            "site": site_url,
            "period": f"{start} to {end}",
            "indexed_pages_with_impressions": len(rows),
            "pages": [
                {
                    "url": r["keys"][0],
                    "clicks": r.get("clicks", 0),
                    "impressions": r.get("impressions", 0),
                }
                for r in rows
            ],
        }
    except Exception as exc:
        logger.error("GSC crawl-errors error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
