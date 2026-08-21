from app.jobs.contracts import JobEnvelope, JobRisk
from app.jobs.registry import resolve_handler


def test_high_impact_jobs_require_approval():
    job = JobEnvelope(
        kind="shopify.shipping.update",
        idempotency_key="shipping-tenant-date",
        risk=JobRisk.HIGH_IMPACT_MUTATION,
        requested_by="operator@example.com",
    )
    assert job.requires_approval()
    assert job.dry_run is True


def test_read_only_jobs_do_not_require_approval():
    job = JobEnvelope(
        kind="shopify.catalog.audit",
        idempotency_key="catalog-audit-date",
        risk=JobRisk.READ_ONLY,
        requested_by="scheduler",
    )
    assert not job.requires_approval()


def test_registry_rejects_arbitrary_jobs():
    try:
        resolve_handler("python.eval")
    except ValueError as error:
        assert "Unsupported job kind" in str(error)
    else:
        raise AssertionError("arbitrary job kind was accepted")
