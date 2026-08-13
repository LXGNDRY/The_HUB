"""
api/routers/gmc.py — Google Merchant Center API endpoints

Routes:
  GET  /api/gmc/disapprovals          — Live GMC disapprovals + critical item issues
  GET  /api/gmc/product-statuses      — All GMC product statuses (up to 250)
  GET  /api/gmc/shipping-drift        — Compare Shopify vs GMC shipping countries
  GET  /api/gmc/title-rotation/state  — Load title rotation state from GCS
  POST /api/gmc/title-rotation/run    — Trigger GMC title rotation job immediately
"""

import os
import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("gcp-bot.api.gmc")
router = APIRouter()

MERCHANT_ID = os.getenv("GMC_MERCHANT_ID", "")


def _require_merchant_id():
    if not MERCHANT_ID:
        raise HTTPException(status_code=503, detail="GMC_MERCHANT_ID not configured")
    return MERCHANT_ID


def _build_content_service():
    from googleapiclient.discovery import build
    from auth.credentials import get_credentials
    return build("content", "v2.1", credentials=get_credentials(), cache_discovery=False)


# ------------------------------------------------------------------
# GET /api/gmc/disapprovals
# ------------------------------------------------------------------

@router.get("/disapprovals")
def get_disapprovals():
    """
    Fetch current GMC disapprovals and critical item-level issues.
    Mirrors gmc_disapproval_check_job but returns structured data instead of alerting.
    """
    merchant_id = _require_merchant_id()
    try:
        service = _build_content_service()
        statuses = service.productstatuses().list(
            merchantId=merchant_id,
            maxResults=250,
        ).execute()

        disapproved = []
        flagged = []

        for item in statuses.get("resources", []):
            product_id = item.get("productId", "")
            title = item.get("title", product_id)

            for ds in item.get("destinationStatuses", []):
                if ds.get("status") == "disapproved":
                    disapproved.append({"product_id": product_id, "title": title})
                    break

            for issue in item.get("itemLevelIssues", []):
                if issue.get("severity") == "error":
                    flagged.append({
                        "product_id": product_id,
                        "title": title,
                        "issue": issue.get("description", ""),
                        "code": issue.get("code", ""),
                    })
                    break

        return {
            "merchant_id": merchant_id,
            "disapproved_count": len(disapproved),
            "flagged_count": len(flagged),
            "disapproved": disapproved,
            "flagged": flagged,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] get_disapprovals failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# GET /api/gmc/product-statuses
# ------------------------------------------------------------------

@router.get("/product-statuses")
def get_product_statuses(max_results: int = 50):
    """
    List GMC product statuses. max_results capped at 250.
    Returns product_id, title, and destination status summary per product.
    """
    merchant_id = _require_merchant_id()
    max_results = min(max_results, 250)
    try:
        service = _build_content_service()
        resp = service.productstatuses().list(
            merchantId=merchant_id,
            maxResults=max_results,
        ).execute()

        products = []
        for item in resp.get("resources", []):
            dest_statuses = {
                ds.get("destination", ""): ds.get("status", "")
                for ds in item.get("destinationStatuses", [])
            }
            products.append({
                "product_id": item.get("productId", ""),
                "title": item.get("title", ""),
                "destination_statuses": dest_statuses,
                "item_issues_count": len(item.get("itemLevelIssues", [])),
            })

        return {
            "merchant_id": merchant_id,
            "count": len(products),
            "next_page_token": resp.get("nextPageToken"),
            "products": products,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] get_product_statuses failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# GET /api/gmc/shipping-drift
# ------------------------------------------------------------------

@router.get("/shipping-drift")
def get_shipping_drift():
    """
    Compare active Shopify shipping zones against GMC shipping services.
    Returns countries present in one but missing from the other.
    Mirrors gmc_shipping_drift_check_job but returns structured data.
    """
    merchant_id = _require_merchant_id()
    try:
        from modules.shopify import shipping_rates_summary
        service = _build_content_service()

        shopify_zones = shipping_rates_summary()
        shopify_countries = set()
        for zone in shopify_zones.get("zones", []):
            for country in zone.get("countries", []):
                code = country.get("code") or country.get("country_code")
                if code:
                    shopify_countries.add(code.upper())

        gmc_resp = service.shippingsettings().get(
            merchantId=merchant_id, accountId=merchant_id
        ).execute()
        gmc_countries = set()
        for svc in gmc_resp.get("services", []):
            if svc.get("active", False):
                for area in svc.get("deliveryCountries", []):
                    gmc_countries.add(area.upper())

        missing_from_gmc = sorted(shopify_countries - gmc_countries)
        missing_from_shopify = sorted(gmc_countries - shopify_countries)

        return {
            "merchant_id": merchant_id,
            "in_sync": not missing_from_gmc and not missing_from_shopify,
            "shopify_country_count": len(shopify_countries),
            "gmc_country_count": len(gmc_countries),
            "missing_from_gmc": missing_from_gmc,
            "missing_from_shopify": missing_from_shopify,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] get_shipping_drift failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# GET /api/gmc/title-rotation/state
# ------------------------------------------------------------------

@router.get("/title-rotation/state")
def get_title_rotation_state():
    """
    Load the current GMC title rotation state from GCS
    (bucket lb-feed-state, key title_rotation_state.json).
    Requires GCP_SA_KEY_JSON and GMC_MERCHANT_ID.
    """
    sa_key_json = os.getenv("GCP_SA_KEY_JSON", "")
    if not sa_key_json:
        raise HTTPException(status_code=503, detail="GCP_SA_KEY_JSON not configured")
    _require_merchant_id()

    try:
        import sys
        scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from title_rotation_module import load_state

        state = load_state(sa_key_json)
        products_tracked = len(state.get("products", {}))
        return {
            "last_run": state.get("last_run"),
            "products_tracked": products_tracked,
            "state": state,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] get_title_rotation_state failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# POST /api/gmc/title-rotation/run
# ------------------------------------------------------------------

@router.post("/title-rotation/run")
def run_title_rotation():
    """
    Trigger the GMC title rotation job immediately (synchronous).
    Advances rotation decisions and saves state to GCS.
    Requires GCP_SA_KEY_JSON and GMC_MERCHANT_ID.
    """
    _require_merchant_id()
    sa_key_json = os.getenv("GCP_SA_KEY_JSON", "")
    if not sa_key_json:
        raise HTTPException(status_code=503, detail="GCP_SA_KEY_JSON not configured")

    try:
        from scheduler.jobs import gmc_title_rotation_job
        gmc_title_rotation_job()
        return {"status": "completed", "job": "gmc_title_rotation"}
    except Exception as e:
        logger.error("[gmc] run_title_rotation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
