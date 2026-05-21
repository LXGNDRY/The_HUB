"""
modules/secret_manager.py — GCP Secret Manager Module

Migrate bot secrets from env vars / GitHub Actions to GCP Secret Manager.
Provides a unified interface for reading, writing, and rotating secrets
used across the bot's modules.

Benefits over env vars:
  - Audit log of every secret access
  - Automatic versioning (never lose old values)
  - IAM-controlled access (not just anyone with env var access)
  - In-memory caching to reduce API calls

Env vars:
  GCP_PROJECT_ID — target project (already set)

Naming convention for secrets:
  gcp-bot-{name}  e.g. gcp-bot-dashboard-api-key, gcp-bot-shopify-admin-token
"""

import os
import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger("gcp-bot.secret_manager")

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
SECRET_PREFIX = "gcp-bot-"


class SecretManagerModule:
    """
    Interface to GCP Secret Manager.
    Caches secret values in-memory per session to reduce API calls.
    """

    def __init__(self, credentials):
        self.credentials = credentials
        self._client = None
        self._cache: dict[str, str] = {}

    @property
    def client(self):
        if not self._client:
            from google.cloud import secretmanager
            self._client = secretmanager.SecretManagerServiceClient(
                credentials=self.credentials
            )
        return self._client

    def _project_path(self) -> str:
        return f"projects/{PROJECT_ID}"

    def _secret_path(self, secret_id: str) -> str:
        return f"projects/{PROJECT_ID}/secrets/{secret_id}"

    def _version_path(self, secret_id: str, version: str = "latest") -> str:
        return f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version}"

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_secret(self, secret_id: str, version: str = "latest", use_cache: bool = True) -> str:
        """
        Retrieve a secret value by ID.

        Args:
            secret_id:  Secret name (with or without gcp-bot- prefix).
            version:    "latest" or a specific numeric version string.
            use_cache:  Return cached value if available (default True).

        Returns:
            Secret value as string.
        """
        # Normalise name
        if not secret_id.startswith(SECRET_PREFIX):
            secret_id = f"{SECRET_PREFIX}{secret_id}"

        cache_key = f"{secret_id}:{version}"
        if use_cache and cache_key in self._cache:
            logger.debug("[secret_manager] Cache hit: %s", secret_id)
            return self._cache[cache_key]

        name = self._version_path(secret_id, version)
        logger.info("[secret_manager] Fetching secret: %s (v=%s)", secret_id, version)

        response = self.client.access_secret_version(request={"name": name})
        value = response.payload.data.decode("utf-8")

        self._cache[cache_key] = value
        return value

    def get_secret_or_env(self, secret_id: str, env_var: str, default: str = "") -> str:
        """
        Try Secret Manager first, fall back to env var, then default.
        Useful for gradual migration from env vars to Secret Manager.
        """
        try:
            return self.get_secret(secret_id)
        except Exception as e:
            logger.debug("[secret_manager] Secret not found (%s), using env var %s.", e, env_var)
            return os.getenv(env_var, default)

    def list_secrets(self) -> list[dict]:
        """List all secrets in the project (names only, no values)."""
        parent = self._project_path()
        secrets = []
        for secret in self.client.list_secrets(request={"parent": parent}):
            secrets.append({
                "name": secret.name.split("/")[-1],
                "full_name": secret.name,
                "labels": dict(secret.labels),
                "create_time": str(secret.create_time),
            })
        logger.info("[secret_manager] Found %d secret(s).", len(secrets))
        return secrets

    def secret_exists(self, secret_id: str) -> bool:
        """Check if a secret exists without reading its value."""
        if not secret_id.startswith(SECRET_PREFIX):
            secret_id = f"{SECRET_PREFIX}{secret_id}"
        try:
            self.client.get_secret(request={"name": self._secret_path(secret_id)})
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Write / Create
    # ------------------------------------------------------------------

    def create_secret(self, secret_id: str, value: str, labels: dict = None) -> dict:
        """
        Create a new secret with an initial version.

        Args:
            secret_id:  Secret name (gcp-bot- prefix added automatically).
            value:      Initial secret value.
            labels:     Optional metadata labels.

        Returns:
            {"secret_id": str, "version": str}
        """
        if not secret_id.startswith(SECRET_PREFIX):
            secret_id = f"{SECRET_PREFIX}{secret_id}"

        parent = self._project_path()
        secret_body = {
            "replication": {"automatic": {}},
            "labels": labels or {"managed-by": "gcp-bot"},
        }

        logger.info("[secret_manager] Creating secret: %s", secret_id)
        secret = self.client.create_secret(
            request={"parent": parent, "secret_id": secret_id, "secret": secret_body}
        )

        # Add initial version
        version = self.add_secret_version(secret_id, value)
        logger.info("[secret_manager] Secret created with version: %s", version["version"])
        return {"secret_id": secret_id, "version": version["version"]}

    def add_secret_version(self, secret_id: str, value: str) -> dict:
        """
        Add a new version to an existing secret (rotation).

        Args:
            secret_id: Secret name.
            value:     New secret value.

        Returns:
            {"secret_id": str, "version": str}
        """
        if not secret_id.startswith(SECRET_PREFIX):
            secret_id = f"{SECRET_PREFIX}{secret_id}"

        parent = self._secret_path(secret_id)
        payload = {"data": value.encode("utf-8")}

        response = self.client.add_secret_version(
            request={"parent": parent, "payload": payload}
        )
        version = response.name.split("/")[-1]

        # Invalidate cache
        for key in list(self._cache.keys()):
            if key.startswith(f"{secret_id}:"):
                del self._cache[key]

        logger.info("[secret_manager] Added version %s to secret %s.", version, secret_id)
        return {"secret_id": secret_id, "version": version}

    def create_or_update_secret(self, secret_id: str, value: str) -> dict:
        """
        Create a secret if it doesn't exist, otherwise add a new version.
        """
        if self.secret_exists(secret_id):
            return self.add_secret_version(secret_id, value)
        return self.create_secret(secret_id, value)

    # ------------------------------------------------------------------
    # Destroy / Disable
    # ------------------------------------------------------------------

    def disable_secret_version(self, secret_id: str, version: str) -> dict:
        """Disable a specific secret version (recoverable)."""
        if not secret_id.startswith(SECRET_PREFIX):
            secret_id = f"{SECRET_PREFIX}{secret_id}"
        name = self._version_path(secret_id, version)
        response = self.client.disable_secret_version(request={"name": name})
        logger.info("[secret_manager] Disabled version %s of %s.", version, secret_id)
        return {"secret_id": secret_id, "version": version, "state": "DISABLED"}

    def delete_secret(self, secret_id: str) -> bool:
        """
        Permanently delete a secret and all its versions.
        WARNING: This is irreversible.
        """
        if not secret_id.startswith(SECRET_PREFIX):
            secret_id = f"{SECRET_PREFIX}{secret_id}"
        self.client.delete_secret(request={"name": self._secret_path(secret_id)})
        # Clear cache
        self._cache = {k: v for k, v in self._cache.items() if not k.startswith(f"{secret_id}:")}
        logger.warning("[secret_manager] DELETED secret: %s", secret_id)
        return True

    # ------------------------------------------------------------------
    # Bot-specific secret inventory
    # ------------------------------------------------------------------

    BOT_SECRETS = {
        "dashboard-api-key": "DASHBOARD_API_KEY",
        "google-api-key": "GOOGLE_API_KEY",
        "ga4-property-id": "GA4_PROPERTY_ID",
        "gcp-project-id": "GCP_PROJECT_ID",
        "gsc-token-json": "GSC_TOKEN_JSON",
        "gsc-client-secret-json": "GSC_CLIENT_SECRET_JSON",
        "shopify-admin-token": "SHOPIFY_ADMIN_TOKEN",
        "discord-webhook-url": "DISCORD_WEBHOOK_URL",
        "slack-webhook-url": "SLACK_WEBHOOK_URL",
        "sheets-dashboard-id": "SHEETS_DASHBOARD_ID",
        "gtm-account-id": "GTM_ACCOUNT_ID",
    }

    def migrate_env_to_secret_manager(self, dry_run: bool = True) -> dict:
        """
        Migrate all known env var secrets to GCP Secret Manager.

        Args:
            dry_run: If True, list what WOULD be migrated without doing it.

        Returns:
            {
                "migrated": [...],
                "skipped_empty": [...],
                "already_exists": [...],
                "errors": [...],
            }
        """
        results = {"migrated": [], "skipped_empty": [], "already_exists": [], "errors": []}

        for secret_name, env_var in self.BOT_SECRETS.items():
            value = os.getenv(env_var, "")
            if not value:
                results["skipped_empty"].append({"secret": secret_name, "env_var": env_var})
                continue

            if dry_run:
                results["migrated"].append({
                    "secret": secret_name,
                    "env_var": env_var,
                    "dry_run": True,
                    "value_length": len(value),
                })
                continue

            try:
                if self.secret_exists(secret_name):
                    results["already_exists"].append(secret_name)
                else:
                    self.create_secret(secret_name, value)
                    results["migrated"].append(secret_name)
            except Exception as e:
                results["errors"].append({"secret": secret_name, "error": str(e)})
                logger.error("[secret_manager] Migration failed for %s: %s", secret_name, e)

        logger.info(
            "[secret_manager] Migration %s complete. Migrated: %d, Skipped: %d, Existing: %d, Errors: %d",
            "(DRY RUN)" if dry_run else "",
            len(results["migrated"]), len(results["skipped_empty"]),
            len(results["already_exists"]), len(results["errors"]),
        )
        return results

    def clear_cache(self):
        """Clear in-memory secret cache."""
        self._cache.clear()
        logger.info("[secret_manager] Cache cleared.")
