# ADR-0002: Durable jobs instead of in-process cron

- Status: Accepted
- Date: 2026-08-21

## Decision

Cloud Scheduler owns time-based triggers. Cloud Tasks or Pub/Sub owns delivery and retries. Cloud Run Jobs or idempotent worker handlers execute long-running mutations. FastAPI processes do not own production schedules.

## Consequences

Every job gains a persistent run record, idempotency key, bounded retry policy, dead-letter behavior, metrics, and an explicit operator replay path. APScheduler may remain for local development only during migration.
