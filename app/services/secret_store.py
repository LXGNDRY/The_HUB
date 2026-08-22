"""Google Secret Manager storage; the database retains references only."""

from __future__ import annotations

import asyncio
import re

from google.cloud import secretmanager

from app.core.config import settings


def _secret_id(tenant_id: str, provider: str) -> str:
    safe_tenant = re.sub(r"[^a-zA-Z0-9_-]", "-", tenant_id)
    safe_provider = re.sub(r"[^a-zA-Z0-9_-]", "-", provider)
    return f"hub-{safe_tenant}-{safe_provider}"


class SecretStore:
    def __init__(self) -> None:
        self.client = secretmanager.SecretManagerServiceClient()
        self.project_path = f"projects/{settings.GCP_PROJECT_ID}"

    async def put(self, tenant_id: str, provider: str, value: str) -> str:
        if not settings.GCP_PROJECT_ID:
            raise RuntimeError("GCP_PROJECT_ID is required for secret storage.")
        secret_id = _secret_id(tenant_id, provider)
        secret_name = f"{self.project_path}/secrets/{secret_id}"

        def _write() -> str:
            try:
                self.client.get_secret(request={"name": secret_name})
            except Exception:
                self.client.create_secret(
                    request={
                        "parent": self.project_path,
                        "secret_id": secret_id,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )
            version = self.client.add_secret_version(
                request={"parent": secret_name, "payload": {"data": value.encode()}}
            )
            return version.name

        return await asyncio.to_thread(_write)

    async def access(self, version_resource: str) -> str:
        response = await asyncio.to_thread(
            self.client.access_secret_version,
            request={"name": version_resource},
        )
        return response.payload.data.decode()
