# Production readiness gate

`hub-backend` is **not approved for public production use** until every P0 item is checked and evidenced in CI or an attached operational record.

## P0 security

- [ ] Authenticated user/session on every non-health API route
- [ ] Tenant membership and role authorization on every tenant resource
- [ ] Shopify OAuth state, shop, and callback HMAC validation
- [ ] Shopify, Stripe, and Razorpay webhook signature validation
- [ ] Persistent webhook replay protection
- [ ] Secret Manager references replace plaintext tenant credentials
- [ ] Rate limiting and security headers enabled
- [ ] Threat-model review complete

## P0 reliability

- [ ] Database migrations run and roll back in staging
- [ ] Readiness verifies database and required secret configuration
- [ ] Deployment fails and rolls back when readiness fails
- [ ] Scheduled mutations execute through durable workers
- [ ] Idempotency is tested for webhooks and jobs

## Quality gate

- [ ] Required CI passes
- [ ] No critical dependency or container vulnerabilities
- [ ] Unit, integration, authorization, and webhook tests pass
- [ ] Minimum agreed coverage passes
- [ ] Staging smoke test and Shopify development-store test pass
- [ ] Operational runbooks reviewed

## Release authorization

Production requires an explicit reviewed PR, immutable image digest, migration plan, rollback target, and named release owner.
