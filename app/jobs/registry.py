"""Explicit job allowlist; arbitrary function execution is forbidden."""

from collections.abc import Awaitable, Callable

from app.jobs.contracts import JobEnvelope

JobHandler = Callable[[JobEnvelope], Awaitable[dict]]


async def catalog_audit(envelope: JobEnvelope) -> dict:
    return {"status": "scaffolded", "tenant_id": str(envelope.tenant_id), "dry_run": envelope.dry_run}


HANDLERS: dict[str, JobHandler] = {
    "shopify.catalog.audit": catalog_audit,
}


def resolve_handler(kind: str) -> JobHandler:
    try:
        return HANDLERS[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported job kind: {kind}") from exc
