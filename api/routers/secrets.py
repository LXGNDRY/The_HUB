"""
api/routers/secrets.py — Secret Manager API endpoints

Routes:
  GET  /api/secrets                       — List all secrets (names only, no values)
  GET  /api/secrets/{name}/exists         — Check if a secret exists
  POST /api/secrets/{name}                — Create or update a secret
  POST /api/secrets/migrate               — Migrate env vars to Secret Manager (dry_run by default)
  DELETE /api/secrets/{name}/version/{v}  — Disable a specific secret version
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.credentials import get_credentials

logger = logging.getLogger("gcp-bot.api.secrets")
router = APIRouter()


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class CreateSecretRequest(BaseModel):
    value: str
    labels: Optional[dict] = None


class MigrateRequest(BaseModel):
    dry_run: bool = True  # Default to dry run for safety


# ------------------------------------------------------------------
# Module factory
# ------------------------------------------------------------------

def _get_module():
    try:
        from modules.secret_manager import SecretManagerModule
        return SecretManagerModule(get_credentials())
    except Exception as e:
        logger.error("[secrets router] Module init failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("")
def list_secrets():
    """List all secrets in the project (names only — values are never returned)."""
    mod = _get_module()
    try:
        secrets = mod.list_secrets()
        return {"secrets": secrets, "count": len(secrets)}
    except Exception as e:
        logger.error("[secrets] list_secrets failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{secret_name}/exists")
def secret_exists(secret_name: str):
    """Check whether a secret exists without reading its value."""
    mod = _get_module()
    try:
        exists = mod.secret_exists(secret_name)
        return {"secret_name": secret_name, "exists": exists}
    except Exception as e:
        logger.error("[secrets] secret_exists failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{secret_name}")
def create_or_update_secret(secret_name: str, body: CreateSecretRequest):
    """Create a new secret or add a new version if it already exists."""
    mod = _get_module()
    try:
        result = mod.create_or_update_secret(secret_name, body.value)
        return {"status": "ok", "secret_id": result["secret_id"], "version": result.get("version")}
    except Exception as e:
        logger.error("[secrets] create_or_update failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/migrate/env-vars")
def migrate_env_vars(body: MigrateRequest):
    """
    Migrate bot env var secrets to GCP Secret Manager.
    Set dry_run=false to actually execute the migration.
    Defaults to dry_run=true for safety.
    """
    mod = _get_module()
    try:
        result = mod.migrate_env_to_secret_manager(dry_run=body.dry_run)
        return result
    except Exception as e:
        logger.error("[secrets] migrate failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{secret_name}/version/{version}")
def disable_version(secret_name: str, version: str):
    """Disable a specific version of a secret (recoverable — does not delete)."""
    mod = _get_module()
    try:
        result = mod.disable_secret_version(secret_name, version)
        return result
    except Exception as e:
        logger.error("[secrets] disable_version failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
