"""
api/routers/tag_manager.py — Google Tag Manager API endpoints

NOTE: GTM's API rejects service-account email addresses as authorized users
(SA emails like `...@developer.gserviceaccount.com` don't match a Google Account
user identity, which is a hard GTM platform requirement).

All GTM operations are handled via the Pipedream google_tag_manager connector,
which authenticates with user OAuth and works perfectly.

These endpoints return informative 200 responses directing the caller to use
the Pipedream connector instead of surfacing unhelpful 500 errors.

GTM Container: GTM-58KH82X
GTM Account:   6111521813
"""

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("gcp-bot.api.gtm")
router = APIRouter()

GTM_CONTAINER_ID = "GTM-58KH82X"
GTM_ACCOUNT_ID = "6111521813"
PIPEDREAM_NOTE = (
    "GTM API requires user OAuth — service accounts are not accepted as GTM users. "
    "Use the Pipedream google_tag_manager connector (connected via user OAuth) for all GTM operations. "
    f"Container: {GTM_CONTAINER_ID} | Account: {GTM_ACCOUNT_ID}"
)

_INFO_RESPONSE = {
    "status": "ok",
    "note": PIPEDREAM_NOTE,
    "container_id": GTM_CONTAINER_ID,
    "account_id": GTM_ACCOUNT_ID,
    "connector": "google_tag_manager__pipedream",
}


# ------------------------------------------------------------------
# Request models (kept for API documentation / future OAuth upgrade)
# ------------------------------------------------------------------

class CreateHtmlTagRequest(BaseModel):
    name: str
    html: str
    firing_trigger_ids: list[str]
    container_id: Optional[str] = None


class CreateGA4TagRequest(BaseModel):
    name: str
    measurement_id: str
    event_name: str
    event_parameters: Optional[list[dict]] = None
    firing_trigger_ids: Optional[list[str]] = None
    container_id: Optional[str] = None


class PublishWorkspaceRequest(BaseModel):
    version_name: str
    version_notes: str = ""
    container_id: Optional[str] = None


# ------------------------------------------------------------------
# Endpoints — all return helpful redirect info
# ------------------------------------------------------------------

@router.get("/containers")
def list_containers():
    """List GTM containers — use Pipedream connector (SA auth not supported by GTM)."""
    logger.info("[gtm] /containers — redirecting to Pipedream connector")
    return {**_INFO_RESPONSE, "endpoint": "/api/gtm/containers"}


@router.get("/summary")
def container_summary(workspace_id: str = "1", container_id: Optional[str] = None):
    """Container summary — use Pipedream connector."""
    return {**_INFO_RESPONSE, "endpoint": "/api/gtm/summary"}


@router.get("/workspaces")
def list_workspaces(container_id: Optional[str] = None):
    """List workspaces — use Pipedream connector."""
    return {**_INFO_RESPONSE, "endpoint": "/api/gtm/workspaces"}


@router.get("/workspaces/{workspace_id}/status")
def workspace_status(workspace_id: str, container_id: Optional[str] = None):
    """Workspace status — use Pipedream connector."""
    return {**_INFO_RESPONSE, "endpoint": f"/api/gtm/workspaces/{workspace_id}/status"}


@router.get("/workspaces/{workspace_id}/tags")
def list_tags(workspace_id: str, container_id: Optional[str] = None):
    """List tags — use Pipedream connector."""
    return {**_INFO_RESPONSE, "endpoint": f"/api/gtm/workspaces/{workspace_id}/tags"}


@router.get("/workspaces/{workspace_id}/triggers")
def list_triggers(workspace_id: str, container_id: Optional[str] = None):
    """List triggers — use Pipedream connector."""
    return {**_INFO_RESPONSE, "endpoint": f"/api/gtm/workspaces/{workspace_id}/triggers"}


@router.get("/workspaces/{workspace_id}/variables")
def list_variables(workspace_id: str, container_id: Optional[str] = None):
    """List variables — use Pipedream connector."""
    return {**_INFO_RESPONSE, "endpoint": f"/api/gtm/workspaces/{workspace_id}/variables"}


@router.post("/workspaces/{workspace_id}/tags/html")
def create_html_tag(workspace_id: str, body: CreateHtmlTagRequest):
    """Create HTML tag — use Pipedream connector."""
    return {**_INFO_RESPONSE, "endpoint": f"/api/gtm/workspaces/{workspace_id}/tags/html",
            "requested_tag_name": body.name}


@router.post("/workspaces/{workspace_id}/tags/ga4")
def create_ga4_tag(workspace_id: str, body: CreateGA4TagRequest):
    """Create GA4 event tag — use Pipedream connector."""
    return {**_INFO_RESPONSE, "endpoint": f"/api/gtm/workspaces/{workspace_id}/tags/ga4",
            "requested_tag_name": body.name}


@router.post("/workspaces/{workspace_id}/publish")
def publish_workspace(workspace_id: str, body: PublishWorkspaceRequest):
    """Publish workspace — use Pipedream connector."""
    return {**_INFO_RESPONSE, "endpoint": f"/api/gtm/workspaces/{workspace_id}/publish",
            "requested_version_name": body.version_name}
