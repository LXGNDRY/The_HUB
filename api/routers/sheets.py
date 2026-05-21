"""
api/routers/sheets.py — Google Sheets dashboard endpoints

Routes:
  GET  /api/sheets/dashboard              — Get dashboard URL (creates if missing)
  POST /api/sheets/refresh                — Refresh all sheets with live data
  POST /api/sheets/update/ga4             — Update GA4 tab only
  POST /api/sheets/update/gsc             — Update GSC tab only
  POST /api/sheets/update/pagespeed       — Update PageSpeed tab only
  POST /api/sheets/update/billing         — Update Billing tab only
  POST /api/sheets/log                    — Append an event to the Log tab
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.credentials import get_credentials

logger = logging.getLogger("gcp-bot.api.sheets")
router = APIRouter()


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class LogEventRequest(BaseModel):
    event_type: str
    message: str


class RefreshRequest(BaseModel):
    spreadsheet_id: Optional[str] = None  # Overrides SHEETS_DASHBOARD_ID env var


# ------------------------------------------------------------------
# Module factory
# ------------------------------------------------------------------

def _get_module(spreadsheet_id: str = None):
    try:
        from modules.sheets import SheetsModule
        mod = SheetsModule(get_credentials())
        if spreadsheet_id:
            import os
            os.environ["SHEETS_DASHBOARD_ID"] = spreadsheet_id
        return mod
    except Exception as e:
        logger.error("[sheets router] Module init failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _get_live_data():
    """Fetch all live data needed for a full dashboard refresh."""
    from api.routers.analytics import _get_analytics_module
    from api.routers.seo import _get_gsc_service
    from agents.pagespeed_agent import run_pagespeed
    from modules.billing import BillingModule

    data = {}

    try:
        from modules.analytics import AnalyticsModule
        am = AnalyticsModule(get_credentials())
        data["ga4_traffic"] = am.get_traffic_summary()
        data["ga4_pages"] = am.get_top_pages()
    except Exception as e:
        logger.warning("[sheets] GA4 data fetch failed: %s", e)
        data["ga4_traffic"] = {}
        data["ga4_pages"] = {}

    try:
        import os, json
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token_json = os.getenv("GSC_TOKEN_JSON", "")
        if token_json:
            token_data = json.loads(token_json)
            gsc_creds = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes"),
            )
            svc = build("searchconsole", "v1", credentials=gsc_creds, cache_discovery=False)
            # Basic search analytics query
            site_url = os.getenv("GSC_SITE_URL", "https://legendary-branding.com")
            resp = svc.searchanalytics().query(
                siteUrl=site_url,
                body={
                    "startDate": "2026-04-22",
                    "endDate": "2026-05-20",
                    "dimensions": ["query"],
                    "rowLimit": 50,
                }
            ).execute()
            data["gsc_data"] = resp
        else:
            data["gsc_data"] = {}
    except Exception as e:
        logger.warning("[sheets] GSC data fetch failed: %s", e)
        data["gsc_data"] = {}

    try:
        mobile = run_pagespeed(strategy="mobile")
        desktop = run_pagespeed(strategy="desktop")
        data["mobile_ps"] = mobile
        data["desktop_ps"] = desktop
    except Exception as e:
        logger.warning("[sheets] PageSpeed data fetch failed: %s", e)
        data["mobile_ps"] = {}
        data["desktop_ps"] = {}

    try:
        bm = BillingModule(get_credentials())
        data["billing_data"] = bm.get_monthly_spend()
    except Exception as e:
        logger.warning("[sheets] Billing data fetch failed: %s", e)
        data["billing_data"] = {}

    return data


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/dashboard")
def get_dashboard():
    """
    Get the Sheets dashboard URL.
    Returns setup instructions if SHEETS_DASHBOARD_ID is not configured.
    """
    spreadsheet_id = os.getenv("SHEETS_DASHBOARD_ID", "")
    if not spreadsheet_id:
        return {
            "status": "setup_required",
            "note": (
                "SHEETS_DASHBOARD_ID is not configured. "
                "To activate the Sheets dashboard: "
                "(1) Create a Google Sheet at https://sheets.google.com, "
                "(2) Share it with 901935277314-compute@developer.gserviceaccount.com as Editor, "
                "(3) Copy the spreadsheet ID from the URL (/d/<ID>/edit), "
                "(4) Add SHEETS_DASHBOARD_ID as a GitHub secret and redeploy."
            ),
            "sa_email": "901935277314-compute@developer.gserviceaccount.com",
            "create_sheet_url": "https://sheets.new",
        }
    mod = _get_module()
    try:
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        return {
            "spreadsheet_id": spreadsheet_id,
            "url": url,
            "note": "Share this spreadsheet with your Google account to view it.",
        }
    except Exception as e:
        logger.error("[sheets] get_dashboard failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh")
def refresh_dashboard(body: RefreshRequest = RefreshRequest()):
    """
    Refresh all sheets with live data from GA4, GSC, PageSpeed, and Billing.
    This triggers a full data pull — may take 30-60 seconds.
    """
    mod = _get_module(body.spreadsheet_id)
    try:
        live = _get_live_data()
        url = mod.refresh_full_dashboard(
            ga4_traffic=live["ga4_traffic"],
            ga4_pages=live["ga4_pages"],
            gsc_data=live["gsc_data"],
            mobile_ps=live["mobile_ps"],
            desktop_ps=live["desktop_ps"],
            billing_data=live["billing_data"],
        )
        return {"status": "refreshed", "url": url}
    except Exception as e:
        logger.error("[sheets] refresh failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/log")
def log_event(body: LogEventRequest):
    """Append an event entry to the Log sheet for audit trail."""
    mod = _get_module()
    try:
        spreadsheet_id = mod.get_or_create_dashboard()
        mod.log_event(spreadsheet_id, body.event_type, body.message)
        return {"status": "logged", "event_type": body.event_type}
    except Exception as e:
        logger.error("[sheets] log_event failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
