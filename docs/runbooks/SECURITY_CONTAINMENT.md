# Security containment runbook

1. Disable the affected Cloud Run revision or remove public invoker access.
2. Preserve logs and record the incident timeline; do not copy secrets into tickets.
3. Rotate affected provider credentials and revoke prior tokens.
4. Inspect audit events, webhook receipts, job runs, and deployment history.
5. Determine affected tenants, resources, and time range.
6. Restore service using a known-good immutable image digest.
7. Verify readiness, authorization, webhook signatures, and critical Shopify reads.
8. Document root cause, corrective controls, ownership, and follow-up deadline.
