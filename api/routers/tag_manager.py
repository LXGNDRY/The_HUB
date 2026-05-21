"""
api/routers/tag_manager.py — Google Tag Manager API endpoints

Routes:
  GET  /api/gtm/containers                    — List all GTM containers
  GET  /api/gtm/summary                       — Full container summary (tags, triggers, vars)
  GET  /api/gtm/workspaces                    — List workspaces
  GET  /api/gtm/workspaces/{id}/status        — Get workspace pending changes
  GET  /api/gtm/workspaces/{id}/tags          — List all tags
  GET  /api/gtm/workspaces/{id}/triggers      — List all triggers
  GET  /api/gtm/workspaces/{id}/variables     — List all variables
  POST /api/gtm/workspaces/{id}/tags/html     — Create custom HTML tag
  POST /api/gtm/workspaces/{id}/tags/ga4      — Create GA4 event tag
  POST /api/gtm/workspaces/{id}/publish       — Create version and publish workspace
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.credentials import get_credentials

logger = logging.getLogger("gcp-bot.api.gtm")
router = APIRouter()


# ------------------------------------------------------------------
# Request models
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
# Module factory
# ------------------------------------------------------------------

def _get_module():
    try:
        from modules.tag_manager import TagManagerModule
        return TagManagerModule(get_credentials())
    except Exception as e:
        logger.error("[gtm router] Module init failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/containers")
def list_containers():
    """List all GTM containers in the account."""
    mod = _get_module()
    try:
        containers = mod.list_containers()
        return {"containers": containers, "count": len(containers)}
    except Exception as e:
        logger.error("[gtm] list_containers failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
def container_summary(workspace_id: str = "1", container_id: Optional[str] = None):
    """Get a full summary: tag/trigger/variable counts + pending changes."""
    mod = _get_module()
    try:
        return mod.get_container_summary(workspace_id, container_id)
    except Exception as e:
        logger.error("[gtm] container_summary failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces")
def list_workspaces(container_id: Optional[str] = None):
    """List all workspaces in the container."""
    mod = _get_module()
    try:
        workspaces = mod.list_workspaces(container_id)
        return {"workspaces": workspaces, "count": len(workspaces)}
    except Exception as e:
        logger.error("[gtm] list_workspaces failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces/{workspace_id}/status")
def workspace_status(workspace_id: str, container_id: Optional[str] = None):
    """Get pending changes and merge conflicts in a workspace."""
    mod = _get_module()
    try:
        return mod.get_workspace_status(workspace_id, container_id)
    except Exception as e:
        logger.error("[gtm] workspace_status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces/{workspace_id}/tags")
def list_tags(workspace_id: str, container_id: Optional[str] = None):
    """List all tags in a workspace."""
    mod = _get_module()
    try:
        tags = mod.list_tags(workspace_id, container_id)
        return {"tags": tags, "count": len(tags)}
    except Exception as e:
        logger.error("[gtm] list_tags failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces/{workspace_id}/triggers")
def list_triggers(workspace_id: str, container_id: Optional[str] = None):
    """List all triggers in a workspace."""
    mod = _get_module()
    try:
        triggers = mod.list_triggers(workspace_id, container_id)
        return {"triggers": triggers, "count": len(triggers)}
    except Exception as e:
        logger.error("[gtm] list_triggers failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workspaces/{workspace_id}/variables")
def list_variables(workspace_id: str, container_id: Optional[str] = None):
    """List all variables in a workspace."""
    mod = _get_module()
    try:
        variables = mod.list_variables(workspace_id, container_id)
        return {"variables": variables, "count": len(variables)}
    except Exception as e:
        logger.error("[gtm] list_variables failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces/{workspace_id}/tags/html")
def create_html_tag(workspace_id: str, body: CreateHtmlTagRequest):
    """Create a Custom HTML tag in the workspace."""
    mod = _get_module()
    try:
        result = mod.create_custom_html_tag(
            workspace_id, body.name, body.html,
            body.firing_trigger_ids, body.container_id
        )
        return {"status": "created", "tag": result}
    except Exception as e:
        logger.error("[gtm] create_html_tag failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces/{workspace_id}/tags/ga4")
def create_ga4_tag(workspace_id: str, body: CreateGA4TagRequest):
    """Create a GA4 Event tag in the workspace."""
    mod = _get_module()
    try:
        result = mod.create_ga4_event_tag(
            workspace_id, body.name, body.measurement_id, body.event_name,
            body.event_parameters, body.firing_trigger_ids, body.container_id
        )
        return {"status": "created", "tag": result}
    except Exception as e:
        logger.error("[gtm] create_ga4_tag failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workspaces/{workspace_id}/publish")
def publish_workspace(workspace_id: str, body: PublishWorkspaceRequest):
    """Create a new container version and publish it live."""
    mod = _get_module()
    try:
        result = mod.publish_workspace(
            workspace_id, body.version_name, body.version_notes, body.container_id
        )
        return {"status": "published", "result": result}
    except Exception as e:
        logger.error("[gtm] publish_workspace failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
