"""
modules/tag_manager.py — Google Tag Manager API Module

Programmatic access to GTM container configuration.
Read container/workspace/tag info, publish versions, and trigger
GTM actions without needing the GTM web UI.

Container: GTM-58KH82X (account 6111521813)

IMPORTANT — Auth note:
GTM does NOT support service account users in its account/container
user management UI. The API itself works with OAuth2 user credentials.
In Cloud Run, the bot uses ADC/SA credentials which the API accepts
for reading container data (scopes: tagmanager.readonly) but the SA
need not be a named GTM user — it just needs the OAuth scope.

The 404 "not found or permission denied" from the SA is because GTM
container-level access requires the authenticated identity to have
been granted access at the GTM account level. Since the SA cannot be
added as a GTM user, the bot routes GTM read/write operations through
the pre-authenticated Pipedream GTM connector (OAuth user token) for
operations that require container access.

For direct API use: provide user_credentials (OAuth2) at init time.

Supported operations:
  - List containers, workspaces, tags, triggers, variables
  - Get workspace status (unpublished changes)
  - Create/update tags (Google Analytics, custom HTML, conversion tracking)
  - Publish a workspace as a new version
"""

import os
import logging
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger("gcp-bot.tag_manager")

GTM_ACCOUNT_ID = os.getenv("GTM_ACCOUNT_ID", "6111521813")
GTM_CONTAINER_ID = os.getenv("GTM_CONTAINER_ID", "GTM-58KH82X")


class TagManagerModule:
    """
    Interface to the Google Tag Manager API v2.
    All path arguments use the GTM resource path format:
      accounts/{accountId}/containers/{containerId}/workspaces/{workspaceId}
    """

    def __init__(self, credentials):
        self.credentials = credentials
        self._service = None

    @property
    def service(self):
        if not self._service:
            self._service = build(
                "tagmanager", "v2",
                credentials=self.credentials,
                cache_discovery=False,
            )
        return self._service

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _account_path(self) -> str:
        return f"accounts/{GTM_ACCOUNT_ID}"

    def _container_path(self, container_id: str = None) -> str:
        cid = container_id or GTM_CONTAINER_ID
        return f"accounts/{GTM_ACCOUNT_ID}/containers/{cid}"

    def _workspace_path(self, workspace_id: str, container_id: str = None) -> str:
        return f"{self._container_path(container_id)}/workspaces/{workspace_id}"

    # ------------------------------------------------------------------
    # Account & Container
    # ------------------------------------------------------------------

    def list_containers(self) -> list[dict]:
        """List all GTM containers in the account."""
        resp = self.service.accounts().containers().list(
            parent=self._account_path()
        ).execute()
        containers = resp.get("container", [])
        logger.info("[gtm] Found %d container(s).", len(containers))
        return [
            {
                "container_id": c.get("containerId"),
                "public_id": c.get("publicId"),
                "name": c.get("name"),
                "usage_context": c.get("usageContext", []),
                "domain_name": c.get("domainName", []),
                "path": c.get("path"),
            }
            for c in containers
        ]

    def get_container(self, container_id: str = None) -> dict:
        """Get metadata for a specific container."""
        resp = self.service.accounts().containers().get(
            path=self._container_path(container_id)
        ).execute()
        return resp

    # ------------------------------------------------------------------
    # Workspaces
    # ------------------------------------------------------------------

    def list_workspaces(self, container_id: str = None) -> list[dict]:
        """List workspaces in a container."""
        resp = self.service.accounts().containers().workspaces().list(
            parent=self._container_path(container_id)
        ).execute()
        workspaces = resp.get("workspace", [])
        logger.info("[gtm] Found %d workspace(s).", len(workspaces))
        return [
            {
                "workspace_id": w.get("workspaceId"),
                "name": w.get("name"),
                "description": w.get("description", ""),
                "path": w.get("path"),
            }
            for w in workspaces
        ]

    def get_workspace_status(self, workspace_id: str, container_id: str = None) -> dict:
        """
        Get the status of a workspace — pending changes, conflicts, etc.

        Returns:
            {
                "workspace_change": list of changed entities,
                "merge_conflict": list of conflicts,
            }
        """
        resp = self.service.accounts().containers().workspaces().getStatus(
            path=self._workspace_path(workspace_id, container_id)
        ).execute()
        changes = resp.get("workspaceChange", [])
        conflicts = resp.get("mergeConflict", [])
        logger.info(
            "[gtm] Workspace %s status: %d change(s), %d conflict(s).",
            workspace_id, len(changes), len(conflicts),
        )
        return {"workspace_changes": changes, "merge_conflicts": conflicts}

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def list_tags(self, workspace_id: str, container_id: str = None) -> list[dict]:
        """List all tags in a workspace."""
        resp = self.service.accounts().containers().workspaces().tags().list(
            parent=self._workspace_path(workspace_id, container_id)
        ).execute()
        tags = resp.get("tag", [])
        logger.info("[gtm] Found %d tag(s) in workspace %s.", len(tags), workspace_id)
        return [
            {
                "tag_id": t.get("tagId"),
                "name": t.get("name"),
                "type": t.get("type"),
                "firing_trigger_ids": t.get("firingTriggerId", []),
                "paused": t.get("paused", False),
                "path": t.get("path"),
            }
            for t in tags
        ]

    def get_tag(self, workspace_id: str, tag_id: str, container_id: str = None) -> dict:
        """Get full details of a specific tag."""
        path = f"{self._workspace_path(workspace_id, container_id)}/tags/{tag_id}"
        return self.service.accounts().containers().workspaces().tags().get(
            path=path
        ).execute()

    def create_custom_html_tag(
        self,
        workspace_id: str,
        name: str,
        html: str,
        firing_trigger_ids: list[str],
        container_id: str = None,
    ) -> dict:
        """
        Create a Custom HTML tag in a workspace.

        Args:
            workspace_id:       Target workspace.
            name:               Tag name (e.g. "LB - Purchase Event Tracker").
            html:               Raw HTML/JS to inject.
            firing_trigger_ids: List of trigger IDs that fire this tag.
        """
        body = {
            "name": name,
            "type": "html",
            "parameter": [
                {"type": "TEMPLATE", "key": "html", "value": html},
                {"type": "BOOLEAN", "key": "supportDocumentWrite", "value": "false"},
            ],
            "firingTriggerId": firing_trigger_ids,
        }
        resp = self.service.accounts().containers().workspaces().tags().create(
            parent=self._workspace_path(workspace_id, container_id),
            body=body,
        ).execute()
        logger.info("[gtm] Created Custom HTML tag: %s (id=%s)", name, resp.get("tagId"))
        return resp

    def create_ga4_event_tag(
        self,
        workspace_id: str,
        name: str,
        measurement_id: str,
        event_name: str,
        event_parameters: list[dict] = None,
        firing_trigger_ids: list[str] = None,
        container_id: str = None,
    ) -> dict:
        """
        Create a GA4 Event tag in a workspace.

        Args:
            measurement_id:   GA4 Measurement ID (e.g. "G-XXXXXXXX").
            event_name:       GA4 event name (e.g. "purchase").
            event_parameters: List of {"name": str, "value": str} dicts.
        """
        params = [
            {"type": "TEMPLATE", "key": "measurementId", "value": measurement_id},
            {"type": "TEMPLATE", "key": "eventName", "value": event_name},
        ]
        if event_parameters:
            params.append({
                "type": "LIST",
                "key": "eventParameters",
                "list": [
                    {
                        "type": "MAP",
                        "map": [
                            {"type": "TEMPLATE", "key": "name", "value": p["name"]},
                            {"type": "TEMPLATE", "key": "value", "value": p["value"]},
                        ],
                    }
                    for p in event_parameters
                ],
            })

        body = {
            "name": name,
            "type": "googtag",
            "parameter": params,
            "firingTriggerId": firing_trigger_ids or [],
        }
        resp = self.service.accounts().containers().workspaces().tags().create(
            parent=self._workspace_path(workspace_id, container_id),
            body=body,
        ).execute()
        logger.info("[gtm] Created GA4 Event tag: %s (id=%s)", name, resp.get("tagId"))
        return resp

    def pause_tag(self, workspace_id: str, tag_id: str, container_id: str = None) -> dict:
        """Pause a tag (prevents it from firing without deleting it)."""
        path = f"{self._workspace_path(workspace_id, container_id)}/tags/{tag_id}"
        tag = self.service.accounts().containers().workspaces().tags().get(path=path).execute()
        tag["paused"] = True
        resp = self.service.accounts().containers().workspaces().tags().update(
            path=path, body=tag
        ).execute()
        logger.info("[gtm] Paused tag: %s", tag_id)
        return resp

    # ------------------------------------------------------------------
    # Triggers
    # ------------------------------------------------------------------

    def list_triggers(self, workspace_id: str, container_id: str = None) -> list[dict]:
        """List all triggers in a workspace."""
        resp = self.service.accounts().containers().workspaces().triggers().list(
            parent=self._workspace_path(workspace_id, container_id)
        ).execute()
        triggers = resp.get("trigger", [])
        return [
            {
                "trigger_id": t.get("triggerId"),
                "name": t.get("name"),
                "type": t.get("type"),
                "path": t.get("path"),
            }
            for t in triggers
        ]

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def list_variables(self, workspace_id: str, container_id: str = None) -> list[dict]:
        """List all variables in a workspace."""
        resp = self.service.accounts().containers().workspaces().variables().list(
            parent=self._workspace_path(workspace_id, container_id)
        ).execute()
        variables = resp.get("variable", [])
        return [
            {
                "variable_id": v.get("variableId"),
                "name": v.get("name"),
                "type": v.get("type"),
                "path": v.get("path"),
            }
            for v in variables
        ]

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def create_version(
        self,
        workspace_id: str,
        version_name: str,
        version_notes: str = "",
        container_id: str = None,
    ) -> dict:
        """
        Create a new container version from a workspace.
        This does NOT publish — it creates a version you can then publish.

        Returns:
            containerVersion object.
        """
        body = {"name": version_name, "notes": version_notes}
        resp = self.service.accounts().containers().workspaces().create_version(
            path=self._workspace_path(workspace_id, container_id),
            body=body,
        ).execute()
        version_id = resp.get("containerVersion", {}).get("containerVersionId")
        logger.info("[gtm] Created version: %s (id=%s)", version_name, version_id)
        return resp

    def publish_version(self, version_id: str, container_id: str = None) -> dict:
        """
        Publish a container version live.

        Args:
            version_id: The numeric version ID to publish.

        Returns:
            publishStatus object.
        """
        path = f"{self._container_path(container_id)}/versions/{version_id}"
        resp = self.service.accounts().containers().versions().publish(
            path=path
        ).execute()
        logger.info("[gtm] Published version %s.", version_id)
        return resp

    def publish_workspace(
        self,
        workspace_id: str,
        version_name: str,
        version_notes: str = "",
        container_id: str = None,
    ) -> dict:
        """
        Create a version from workspace and immediately publish it.
        Convenience wrapper for create_version + publish_version.

        Returns:
            {"version": ..., "publish_status": ...}
        """
        version_resp = self.create_version(workspace_id, version_name, version_notes, container_id)
        version_id = version_resp.get("containerVersion", {}).get("containerVersionId")
        if not version_id:
            raise RuntimeError("create_version did not return a containerVersionId.")
        publish_resp = self.publish_version(version_id, container_id)
        logger.info("[gtm] Workspace %s published as version %s.", workspace_id, version_id)
        return {"version": version_resp, "publish_status": publish_resp}

    # ------------------------------------------------------------------
    # Convenience summary
    # ------------------------------------------------------------------

    def get_container_summary(self, workspace_id: str = "1", container_id: str = None) -> dict:
        """
        Get a full summary of the container state: tags, triggers, variables, status.
        """
        tags = self.list_tags(workspace_id, container_id)
        triggers = self.list_triggers(workspace_id, container_id)
        variables = self.list_variables(workspace_id, container_id)
        status = self.get_workspace_status(workspace_id, container_id)

        return {
            "container_id": container_id or GTM_CONTAINER_ID,
            "workspace_id": workspace_id,
            "tag_count": len(tags),
            "trigger_count": len(triggers),
            "variable_count": len(variables),
            "tags": tags,
            "triggers": triggers,
            "variables": variables,
            "pending_changes": len(status.get("workspace_changes", [])),
            "merge_conflicts": len(status.get("merge_conflicts", [])),
        }
