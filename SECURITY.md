# Security policy

## Supported branches

Only `main` is considered deployable. Security fixes are developed in short-lived branches and merged through reviewed pull requests with mandatory CI.

## Reporting

Do not open a public issue containing credentials, customer data, exploit details, or payment information. Report vulnerabilities privately to the repository owner and include affected component, reproduction steps, impact, and suggested containment.

## Non-negotiable controls

- Never commit access tokens, private keys, service-account JSON, webhook secrets, or customer data.
- Every public webhook verifies the provider signature against the unmodified body before parsing.
- Every tenant query is authorized against the authenticated principal.
- Store secret references in the application database; store secret material in Secret Manager.
- Production mutations require an audit entry, idempotency key, bounded batch, and rollback information.
- `hub-backend` remains quarantined until the production-readiness gate in `docs/PRODUCTION_READINESS.md` passes.
