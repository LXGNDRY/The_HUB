"""
SEO router — Google Search Console integration.
Prefix in main.py: /api/seo
"""

import logging
from fastapi import APIRouter, HTTPException
from config import settings

logger = logging.getLogger("gcp-bot.seo")
router = APIRouter()


def _gsc_client():
    """Build an authenticated GSC client via google-api-python-client."""
    from googleapiclient.discovery import build
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        settings.google_service_account_key_path,
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
    )
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


@router.get("/crawl-errors", summary="GSC crawl errors")
def crawl_errors(site_url: str = "https://legendary-branding.com"):
    """
    Returns URL inspection / crawl error summary for the site.
    """
    try:
        service = _gsc_client()
        resp = (
            service.urlcrawlerrorscounts()
            .query(
                siteUrl=site_url,
                platform="web",
                category="notFound",
                latestCountsOnly=True,
            )
            .execute()
        )
        return {"site": site_url, "crawl_errors": resp}
    except Exception as exc:
        logger.error("GSC crawl-errors error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
