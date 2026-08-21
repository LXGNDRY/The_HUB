# The HUB target architecture

## Service boundaries

| Service | Responsibility | Data boundary | Deployment |
|---|---|---|---|
| `gcp-bot` | Legendary Branding single-store operations | Legendary-only credentials and operational state | Independent Cloud Run service |
| `hub-backend` | CTO.new authenticated multi-tenant control plane | Tenant-scoped database records and secret references | Independent Cloud Run service |
| `razorpay-backend` | Payment-provider integration | Payment events and provider secrets only | Independent Cloud Run service |
| workers | Durable Shopify/GMC/content mutations | Idempotent job and event records | Cloud Run Jobs / Cloud Tasks |

## Dependency rules

1. HTTP routers validate transport and authorization, then call services.
2. Services implement business policy and tenant boundaries.
3. Integration clients own protocol behavior, retries, timeouts, and rate limits.
4. Workers own asynchronous and scheduled mutations.
5. No service imports another service's HTTP layer.
6. No script implements Shopify authentication independently.

## Required production topology

- Cloud Scheduler creates durable job requests; web processes do not own cron state.
- Pub/Sub or Cloud Tasks provides retries and dead-letter handling.
- Secret Manager holds all third-party credentials.
- Workload Identity Federation replaces downloadable GCP service-account keys.
- PostgreSQL records tenants, memberships, audit events, webhook receipts, idempotency keys, and job runs.
- Each service has a distinct runtime service account with least-privilege IAM.
