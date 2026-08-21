# Enterprise bootstrap implementation

## Delivery sequence

1. Contain unsafe SaaS endpoints and rotate exposed credentials.
2. Establish mandatory CI, dependency scanning, secret scanning, and tests.
3. Implement identity, sessions, tenant memberships, and role authorization.
4. Complete secure Shopify OAuth and encrypted secret-reference storage.
5. Verify and deduplicate all provider webhooks.
6. Consolidate Shopify clients and migrate REST resources to GraphQL.
7. Move scheduled work to Cloud Scheduler plus durable workers.
8. Split service dependencies, images, identities, and deployment pipelines.
9. Add catalog governance, mutation journals, approval policies, and rollback tooling.
10. Pass the production-readiness gate in staging before public enablement.

## Vertical-slice rule

Each slice must include code, tests, documentation, migration impact, observability, rollback behavior, and a passing CI run. High-impact Shopify mutations remain disabled until their slice passes staging verification.
