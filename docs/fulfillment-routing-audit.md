# LB-FUL-001 — Fulfillment routing diagnostic (draft)

This tool is **read-only and offline**. It consumes a manually exported snapshot and never changes Shopify configuration. The snapshot schema is deliberately minimal and is **not** an assertion that Shopify API fields have identical names. An exporter must map authoritative Shopify data to these keys and record source IDs, pagination and coverage.

Run from the repository root:

```bash
python -m unittest discover -s tests -p 'test_fulfillment_routing_audit.py'
python scripts/fulfillment_routing_audit.py snapshot.json --output routing-report.json
```

The tool flags brand location shipping eligibility, missing eligible shipping origins, duplicates and incomplete data. Exit code 0 = no detected exceptions, 2 = exceptions or incomplete. A clean result is **not** evidence that shipping prices, country coverage, order routing rules or third-party POD fulfillment were validated.

## Next non-destructive tasks

1. Build an authenticated read-only Shopify exporter with pagination and inventory/fulfillment scopes.
2. Reconcile location enumeration against delivery profile origins and third-party fulfillment services.
3. Extend snapshots to include delivery zones, market availability, inventory quantities and source timestamps.
4. Validate against known orders and controlled non-purchasing checkout tests.
5. Review any proposed Shopify settings change separately with owner approval.

## Rollback

Revert this feature branch or PR. No Shopify data is written.
