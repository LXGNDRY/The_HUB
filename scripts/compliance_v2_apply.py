#!/usr/bin/env python3
"""
compliance_v2_apply.py — Legendary Branding

Manual, single-item write path for Compliance V2. Re-evaluates the variant
fresh at apply time and re-checks it against Shopify's current live state
before writing (app/core/international_compliance/remediation.py's staleness
check) — it never trusts a plan computed earlier without re-verifying it.

No human approval is required to apply a write: the safety guarantee is
entirely upstream in the classifier/policy fail-closed design
(plan_compliance_write() only ever produces a plan for evidence-verified,
high/verified-confidence classifications) plus the staleness re-check here.
--approved-by/--approval-reference are optional audit-trail labels only —
omit them and this defaults to an automation identity.

For bulk automated writes across the whole catalog (what actually runs
nightly), see modules/international_compliance_runner.py::apply_ready_plans().
This script is for a single, manually-triggered write by inventory item.

Defaults to --dry-run behavior (no --apply flag = print the plan, write
nothing).

Usage:
  # Preview only — always safe, never writes:
  python scripts/compliance_v2_apply.py --inventory-item-id gid://shopify/InventoryItem/123

  # Actually write:
  python scripts/compliance_v2_apply.py --inventory-item-id gid://shopify/InventoryItem/123 --apply
"""

import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from app.core.international_compliance.audit import ShopifyComplianceSnapshot  # noqa: E402
from app.core.international_compliance.orchestrator import evaluate_variant  # noqa: E402
from app.core.international_compliance.persistence import (  # noqa: E402
    execute_compliance_write,
    plan_compliance_write,
)
from app.core.international_compliance.remediation import (  # noqa: E402
    RemediationApproval,
    RemediationApprovalError,
    StaleRemediationPlanError,
    authorize_remediation,
)
from modules.international_compliance_runner import (  # noqa: E402
    ShopifyComplianceWriter,
    fetch_variant_record_by_inventory_item,
    load_supplier_registry,
)

_DEFAULT_APPROVED_BY = "compliance_v2_automation"


def main():
    parser = argparse.ArgumentParser(description="Compliance V2 single-item write (manual/on-demand)")
    parser.add_argument("--inventory-item-id", required=True, help="gid://shopify/InventoryItem/...")
    parser.add_argument("--approved-by", default=_DEFAULT_APPROVED_BY, help="Optional audit-trail label for who/what triggered this write")
    parser.add_argument("--approval-reference", default=None, help="Optional audit-trail label/reason for this write")
    parser.add_argument("--confirm-fingerprint", default=None, help="Optional: abort if the live classification fingerprint has changed since you reviewed it")
    parser.add_argument("--apply", action="store_true", help="Actually write to Shopify. Without this flag, only prints the plan.")
    args = parser.parse_args()

    registry, bindings = load_supplier_registry()
    record = fetch_variant_record_by_inventory_item(args.inventory_item_id)
    binding = bindings.get(record.variant_id)

    evaluation = evaluate_variant(record, registry=registry, supplier_binding=binding)
    item = evaluation.item

    if args.confirm_fingerprint and item.fingerprint() != args.confirm_fingerprint:
        print("ERROR: live classification fingerprint has changed since you reviewed this plan.", file=sys.stderr)
        print("Re-run compliance_v2_audit.py and review the new plan before applying.", file=sys.stderr)
        sys.exit(1)

    current = ShopifyComplianceSnapshot(
        hs_code=record.compliance.hs_code,
        country_of_origin=record.compliance.country_of_origin,
        weight_grams=record.compliance.weight_grams,
        taxonomy=record.compliance.taxonomy,
    )

    plan = plan_compliance_write(args.inventory_item_id, item, current)
    if plan is None:
        print(f"No write needed or not READY. Review state: {evaluation.decision.review_state.value}")
        print(f"Reasons: {', '.join(evaluation.decision.reasons)}")
        sys.exit(0)

    print("Planned write:")
    print(f"  Inventory item:  {plan.inventory_item_id}")
    print(f"  HS code:         {plan.old_hs_code or '(none)'} -> {plan.new_hs_code}")
    print(f"  Country of origin: {plan.old_country_of_origin or '(none)'} -> {plan.new_country_of_origin}")
    print(f"  Weight (g):      {plan.old_weight_grams or '(none)'} -> {plan.new_weight_grams}")
    print(f"  Rule version:    {plan.rule_version}")
    print(f"  Reasons:         {', '.join(plan.reasons)}")

    if not args.apply:
        print("\nDry run only (pass --apply to write). Nothing was changed.")
        return

    approval_reference = args.approval_reference or (
        f"manual CLI apply {datetime.now(timezone.utc).isoformat()}, rule_version={plan.rule_version}"
    )
    approval = RemediationApproval(
        inventory_item_id=plan.inventory_item_id,
        classification_fingerprint=plan.classification_fingerprint,
        approved_hs6=plan.new_hs_code,
        approved_country_of_origin=plan.new_country_of_origin,
        approved_weight_grams=plan.new_weight_grams,
        approved_by=args.approved_by,
        approval_reference=approval_reference,
    )

    try:
        authorized_plan = authorize_remediation(plan, approval, current)
    except (RemediationApprovalError, StaleRemediationPlanError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    applied = execute_compliance_write(ShopifyComplianceWriter(), authorized_plan, dry_run=False)
    if applied:
        print(f"\n✅ Written to Shopify ({args.approved_by}: {approval_reference}).")
    else:
        print("\nNo write performed.")


if __name__ == "__main__":
    main()
