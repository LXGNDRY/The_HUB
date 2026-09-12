# ADR-0001: Separate service boundaries

- Status: Accepted
- Date: 2026-08-21

## Decision

Legendary Branding's `gcp-bot`, the CTO.new `hub-backend`, and the Razorpay adapter remain independently deployed services. They receive independent dependency locks, runtime identities, CI gates, images, configuration, readiness checks, and rollback targets.

## Consequences

Shared code must be packaged as a narrow library rather than imported across service HTTP layers. A change to one service cannot implicitly deploy another service. This adds some pipeline configuration but sharply reduces operational and credential blast radius.
