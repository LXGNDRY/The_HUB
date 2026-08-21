# Enterprise hardening status

## Implemented on the hardening branch

- SaaS quarantine and private-by-default deployment
- Signed session validation and principal propagation
- Membership-based tenant authorization
- Shopify OAuth callback signature and state verification
- Secret Manager-backed Shopify token storage
- Persistent webhook replay protection
- Verified Shopify, Stripe, and Razorpay signatures
- Stripe billing-state persistence
- GraphQL-first Shopify client foundation
- Alembic enterprise security migration
- Durable job envelope, allowlist, atomic claim, and run record
- Cloud Run Job and Pub/Sub Terraform scaffold
- CI, tests, scanning, threat model, ADRs, and containment runbook

## Still gated before production

- Connect the selected external identity provider and session issuer
- Create the first system administrator and tenant-owner memberships
- Migrate any existing plaintext tenant credentials before running migration 0001
- Replace the temporary in-process webhook response path with Pub/Sub/Cloud Tasks enqueueing
- Implement tenant-aware Shopify catalog handlers on the shared client
- Split and lock dependencies by service
- Replace GitHub GCP JSON credentials with Workload Identity Federation
- Add remote Terraform state and reviewed staging environment plan
- Run migrations, integration tests, Shopify development-store tests, payment test events, and rollback exercise
- Satisfy every item in `docs/PRODUCTION_READINESS.md`
