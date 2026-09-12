# Scheduler migration matrix

Production target: Cloud Scheduler → durable queue/job → persistent run record. APScheduler remains a compatibility bridge only.

| Existing job | Risk | Target | Approval |
|---|---|---|---|
| Billing, quota, VM health, logs, storage audits | Read-only | Cloud Run Job | No |
| Sheets and analytics refresh | Reversible | Cloud Run Job | No |
| Search indexing and IndexNow submissions | Reversible | Cloud Tasks | No |
| Product health, GMC disapproval, shipping drift, Klaviyo health | Read-only | Cloud Run Job | No |
| Alt text, compliance, product type, product weight patches | Reversible mutation | Cloud Run Job | Dry-run evidence |
| Market health corrections | High-impact mutation | Cloud Run Job | Required |
| GMC auto-fix and shipping synchronization | High-impact mutation | Cloud Run Job | Required |
| GMC title rotation | High-impact mutation | Cloud Run Job | Required |
| Blog writer | Content mutation | Draft queue only | Editorial approval |
| VM stop, snapshot delete | High-impact infrastructure mutation | Cloud Run Job | Required |

## Migration gate

Each migrated job needs a stable idempotency-key formula, bounded page/batch size, timeout, retry budget, dead-letter destination, dry-run mode, before/after audit record, rollback reference, metrics, and operator replay procedure. The embedded schedule must be disabled only after the external schedule succeeds twice in staging without duplicate side effects.
