"""Atomic job claiming and terminal-state recording."""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.contracts import JobEnvelope
from app.models.jobs import JobRun


async def claim_job(db: AsyncSession, envelope: JobEnvelope) -> JobRun | None:
    run = JobRun(
        id=envelope.id,
        tenant_id=envelope.tenant_id,
        kind=envelope.kind,
        idempotency_key=envelope.idempotency_key,
        requested_by=envelope.requested_by,
        payload=envelope.payload,
    )
    db.add(run)
    try:
        await db.commit()
        return run
    except IntegrityError:
        await db.rollback()
        return None


async def finish_job(db: AsyncSession, run: JobRun, status: str, result: dict) -> None:
    run.status = status
    run.result = result
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()
