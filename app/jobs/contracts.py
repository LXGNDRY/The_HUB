"""Durable job contracts shared by enqueueing APIs and workers."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class JobRisk(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE_MUTATION = "reversible_mutation"
    HIGH_IMPACT_MUTATION = "high_impact_mutation"


class JobEnvelope(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID | None = None
    kind: str
    idempotency_key: str = Field(min_length=8, max_length=255)
    risk: JobRisk
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_by: str
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dry_run: bool = True
    approval_id: UUID | None = None

    def requires_approval(self) -> bool:
        return self.risk == JobRisk.HIGH_IMPACT_MUTATION


class JobResult(BaseModel):
    job_id: UUID
    succeeded: bool
    attempts: int = Field(ge=1)
    started_at: datetime
    finished_at: datetime
    summary: dict[str, Any] = Field(default_factory=dict)
    rollback_reference: str | None = None
