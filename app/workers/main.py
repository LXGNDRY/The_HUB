"""Cloud Run Job entry point for idempotent, allowlisted work."""

import asyncio
import json
import os

from app.database import async_session
from app.jobs.contracts import JobEnvelope
from app.jobs.registry import resolve_handler
from app.jobs.repository import claim_job, finish_job


async def run() -> int:
    envelope = JobEnvelope.model_validate(json.loads(os.environ["JOB_ENVELOPE_JSON"]))
    if envelope.requires_approval() and envelope.approval_id is None:
        raise RuntimeError("High-impact job requires an approval reference.")
    async with async_session() as db:
        job_run = await claim_job(db, envelope)
        if job_run is None:
            return 0
        try:
            result = await resolve_handler(envelope.kind)(envelope)
            await finish_job(db, job_run, "succeeded", result)
            return 0
        except Exception as exc:
            await finish_job(db, job_run, "failed", {"error_type": type(exc).__name__})
            raise


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
