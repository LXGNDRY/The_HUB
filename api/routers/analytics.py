"""
Analytics router — Google Analytics 4 (Data API) integration.
Prefix in main.py: /api/analytics

Logic lives in modules/analytics.py. This router is a thin HTTP wrapper.
"""

import logging
from fastapi import APIRouter, HTTPException
from modules.analytics import AnalyticsModule

logger = logging.getLogger("gcp-bot.analytics")
router = APIRouter()

_analytics = AnalyticsModule()


@router.get("/traffic", summary="GA4 traffic overview (sessions, users, bounce rate by date)")
def traffic_overview(days: int = 28):
    try:
        return _analytics.get_traffic_summary(days=days)
    except Exception as exc:
        logger.error("GA4 traffic error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/top-pages", summary="GA4 top pages by sessions")
def top_pages(days: int = 28, limit: int = 20):
    try:
        return _analytics.get_top_pages(days=days, limit=limit)
    except Exception as exc:
        logger.error("GA4 top-pages error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/countries", summary="GA4 sessions + conversions by country (international traffic view)")
def country_breakdown(days: int = 28):
    try:
        return _analytics.get_country_breakdown(days=days)
    except Exception as exc:
        logger.error("GA4 country breakdown error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sources", summary="GA4 sessions + conversions by source/medium (ads vs organic split)")
def source_medium_breakdown(days: int = 28):
    try:
        return _analytics.get_source_medium_breakdown(days=days)
    except Exception as exc:
        logger.error("GA4 source/medium breakdown error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
