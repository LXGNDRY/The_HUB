# ADR-0003: One GraphQL-first Shopify client

- Status: Accepted
- Date: 2026-08-21

## Decision

Every service and workflow uses a shared tenant-bound Shopify client. Tokens are supplied by an injected provider backed by Secret Manager; operations never accept a raw token argument. New operations use the GraphQL Admin API. Existing REST calls are migrated by resource domain and tracked until removal.

## Consequences

Authentication, deadlines, retry budgets, throttle behavior, error mapping, telemetry, and API versioning are implemented once. Standalone scripts may call the package but may not perform their own OAuth exchange.
