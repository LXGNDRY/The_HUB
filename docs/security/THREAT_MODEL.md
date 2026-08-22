# Threat model

## Protected assets

- Shopify Admin tokens and merchant data
- GCP credentials and infrastructure controls
- Stripe and Razorpay billing state
- Klaviyo customer and campaign data
- Tenant identity, authorization, and audit records

## Primary threats and controls

| Threat | Impact | Mandatory control |
|---|---|---|
| Cross-tenant IDOR | Merchant takeover/data exposure | Principal-to-tenant membership check on every request |
| Forged webhook | Unauthorized mutation/billing changes | Raw-body signature verification and replay protection |
| OAuth CSRF or shop substitution | Token bound to attacker-controlled shop | Signed one-time state, callback HMAC, strict shop validation |
| Database compromise | All provider tokens exposed | Secret references only; secret material in Secret Manager |
| Duplicate event/job | Repeated product, inventory, or payment mutation | Persistent idempotency keys and atomic claims |
| Compromised CI | Production and secret compromise | OIDC federation, minimal permissions, protected environments |
| Autonomous bad mutation | Catalog or shipping outage | Dry run, approval policy, batch limits, audit/rollback record |

## Trust boundaries

The public internet, Shopify, payment providers, GitHub Actions, Cloud Run, Cloud SQL, and background workers are separate trust boundaries. Data crossing a boundary must be authenticated, validated, bounded, and logged without sensitive values.
