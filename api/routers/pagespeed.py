"""
PageSpeed router — Google PageSpeed Insights API.
Prefix in main.py: /api/pagespeed
"""

import os
import logging
import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger("gcp-bot.pagespeed")
router = APIRouter()

PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")


@router.get("/report", summary="PageSpeed Insights report")
def pagespeed_report(
    url: str = "https://legendary-branding.com",
    strategy: str = "mobile",
):
    """
    Runs a PageSpeed Insights audit for the given URL.
    strategy: 'mobile' | 'desktop'
    Returns Core Web Vitals + Lighthouse performance score.
    """
    try:
        params = {
            "url": url,
            "strategy": strategy,
            "category": "performance",
        }
        api_key = GOOGLE_API_KEY or os.getenv("GOOGLE_API_KEY", "")
        if api_key:
            params["key"] = api_key

        resp = httpx.get(PSI_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        categories = data.get("lighthouseResult", {}).get("categories", {})
        audits = data.get("lighthouseResult", {}).get("audits", {})
        loading_exp = data.get("loadingExperience", {})

        def _metric(key: str):
            a = audits.get(key, {})
            return {
                "display": a.get("displayValue", "n/a"),
                "score": a.get("score"),
            }

        return {
            "url": url,
            "strategy": strategy,
            "performance_score": round(
                (categories.get("performance", {}).get("score") or 0) * 100
            ),
            "field_data_overall": loading_exp.get("overall_category", "n/a"),
            "metrics": {
                "first_contentful_paint": _metric("first-contentful-paint"),
                "largest_contentful_paint": _metric("largest-contentful-paint"),
                "total_blocking_time": _metric("total-blocking-time"),
                "cumulative_layout_shift": _metric("cumulative-layout-shift"),
                "speed_index": _metric("speed-index"),
                "interactive": _metric("interactive"),
            },
        }
    except httpx.HTTPStatusError as exc:
        logger.error("PSI HTTP error: %s", exc)
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))
    except Exception as exc:
        logger.error("PSI error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
