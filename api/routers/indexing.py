"""
api/routers/indexing.py — Web Search Indexing API endpoints

Routes:
  POST /api/indexing/submit               — Submit a single URL
  POST /api/indexing/submit-batch         — Submit multiple URLs
  POST /api/indexing/submit-sitemap       — Parse sitemap and submit all URLs
  POST /api/indexing/submit-products      — Submit product URLs by handle
  GET  /api/indexing/status               — Get URL notification status
  GET  /api/indexing/quota                — Check daily quota usage
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.credentials import get_credentials

logger = logging.getLogger("gcp-bot.api.indexing")
router = APIRouter()


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class SubmitUrlRequest(BaseModel):
    url: str
    action: str = "URL_UPDATED"  # "URL_UPDATED" | "URL_DELETED"


class SubmitBatchRequest(BaseModel):
    urls: list[str]
    action: str = "URL_UPDATED"


class SubmitSitemapRequest(BaseModel):
    sitemap_url: Optional[str] = None
    dry_run: bool = False


class SubmitProductsRequest(BaseModel):
    product_handles: list[str]
    base_url: Optional[str] = None


# ------------------------------------------------------------------
# Module factory — new instance per request so credentials stay fresh
# ------------------------------------------------------------------

def _get_module():
    try:
        from modules.indexing import IndexingModule
        return IndexingModule(get_credentials())
    except Exception as e:
        logger.error("[indexing router] Module init failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/submit")
def submit_url(body: SubmitUrlRequest):
    """Submit a single URL to Google's Indexing API."""
    mod = _get_module()
    try:
        result = mod.submit_url(body.url, action=body.action)
        quota = mod.get_quota_status()
        return {"submitted": body.url, "action": body.action, "response": result, "quota": quota}
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        logger.error("[indexing] submit_url failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit-batch")
def submit_batch(body: SubmitBatchRequest):
    """Submit multiple URLs to Google's Indexing API (respects daily quota)."""
    mod = _get_module()
    try:
        result = mod.submit_urls_batch(body.urls, action=body.action)
        return result
    except Exception as e:
        logger.error("[indexing] submit_batch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit-sitemap")
def submit_sitemap(body: SubmitSitemapRequest):
    """
    Parse the store sitemap and submit all URLs for indexing.
    Use dry_run=true to preview URLs without submitting.
    """
    mod = _get_module()
    try:
        result = mod.submit_sitemap_urls(
            sitemap_url=body.sitemap_url,
            dry_run=body.dry_run,
        )
        return result
    except Exception as e:
        logger.error("[indexing] submit_sitemap failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit-products")
def submit_products(body: SubmitProductsRequest):
    """Submit specific Shopify product URLs by product handle."""
    mod = _get_module()
    try:
        result = mod.submit_new_products(
            body.product_handles,
            base_url=body.base_url,
        )
        return result
    except Exception as e:
        logger.error("[indexing] submit_products failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def url_status(url: str):
    """Check the indexing notification status for a specific URL."""
    mod = _get_module()
    try:
        result = mod.get_url_status(url)
        return result
    except Exception as e:
        logger.error("[indexing] url_status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quota")
def quota_status():
    """Check how many Indexing API submissions have been used today (this session)."""
    mod = _get_module()
    return mod.get_quota_status()
