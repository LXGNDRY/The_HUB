#!/usr/bin/env python3
"""
compliance_v2_apply.py — Legendary Branding

The ONLY path that writes HS code / country of origin to Shopify under
Compliance V2. Requires an explicit human approval (--approved-by,
--approval-reference) and re-evaluates the variant fresh at apply time — it
never trusts a plan computed earlier by compliance_v2_audit.py without
re-checking it against Shopify's current live state first
(app/core/international_compliance/remediation.py's staleness check).

Defaults to --dry-run behavior (no --apply flag = print the plan, write
nothing). This mirrors config.py's safe_execute() convention used elsewhere
in this repo for destructive actions.

Usage:
  # Preview only — always safe, never writes:
  python scripts/compliance_v2_apply.py --inventory-item-id gid://shopify/InventoryItem/123

  # Actually write, after a human has reviewed the plan:
  python scripts/compliance_v2_apply.py --inventory-item-id gid://shopify/InventoryItem/123 \\
      --approved-by "Jane Doe" --approval-reference "reviewed 2026-09-12, ticket LB-482" --apply
"""

import argparse
import sys

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
from app.core.international_compliance.shopify_catalog import parse_product_node  # noqa: E402
from modules.international_compliance_runner import load_supplier_registry  # noqa: E402

FETCH_BY_INVENTORY_ITEM = """
query($id: ID!) {
  inventoryItem(id: $id) {
    id
    variant {
      id
      product {
        id
        title
        status
        vendor
        productType
        category { fullName name }
        tags
        variants(first: 100) {
          nodes {
            id
            title
            sku
            taxable
            availableForSale
            inventoryItem {
              id
              requiresShipping
              harmonizedSystemCode
              countryCodeOfOrigin
              measurement { weight { value unit } }
            }
          }
        }
      }
    }
  }
}
"""

UPDATE_INVENTORY_ITEM = """
mutation inventoryItemUpdate($id: ID!, $input: InventoryItemUpdateInput!) {
  inventoryItemUpdate(id: $id, input: $input) {
    inventoryItem {
      id
      countryCodeOfOrigin
      harmonizedSystemCode
      measurement { weight { value unit } }
    }
    userErrors { field message }
  }
}
"""


class ShopifyComplianceWriter:
    """Concrete ComplianceWriter — the only place that mutates Shopify HS/COO/weight."""

    def apply(self, plan) -> None:
        from modules.shopify import _graphql

        result = _graphql(
            UPDATE_INVENTORY_ITEM,
            {
                "id": plan.inventory_item_id,
                "input": {
                    "harmonizedSystemCode": plan.new_hs_code,
                    "countryCodeOfOrigin": plan.new_country_of_origin,
                    "measurement": {"weight": {"value": plan.new_weight_grams, "unit": "GRAMS"}},
                },
            },
        )
        errors = result.get("data", {}).get("inventoryItemUpdate", {}).get("userErrors", [])
        if errors:
            raise RuntimeError(f"Shopify inventoryItemUpdate userErrors: {errors}")


def fetch_variant_record_by_inventory_item(inventory_item_id: str):
    from modules.shopify import _graphql

    data = _graphql(FETCH_BY_INVENTORY_ITEM, {"id": inventory_item_id})
    inventory_item = data["data"]["inventoryItem"]
    if inventory_item is None:
        raise SystemExit(f"No inventory item found for {inventory_item_id}")
    variant_id = inventory_item["variant"]["id"]
    product = inventory_item["variant"]["product"]

    records = parse_product_node(product)
    for record in records:
        if record.variant_id == variant_id:
            return record
    raise SystemExit(f"Variant {variant_id} not found on its own product node — unexpected.")


def main():
    parser = argparse.ArgumentParser(description="Compliance V2 controlled remediation write")
    parser.add_argument("--inventory-item-id", required=True, help="gid://shopify/InventoryItem/...")
    parser.add_argument("--approved-by", default=None, help="Name of the human approving this write")
    parser.add_argument("--approval-reference", default=None, help="Ticket/reason/date reference for this approval")
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
        print("Re-run compliance_v2_audit.py and review the new plan before approving.", file=sys.stderr)
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

    if not args.approved_by or not args.approval_reference:
        print("\nERROR: --approved-by and --approval-reference are required with --apply.", file=sys.stderr)
        sys.exit(1)

    approval = RemediationApproval(
        inventory_item_id=plan.inventory_item_id,
        classification_fingerprint=plan.classification_fingerprint,
        approved_hs6=plan.new_hs_code,
        approved_country_of_origin=plan.new_country_of_origin,
        approved_weight_grams=plan.new_weight_grams,
        approved_by=args.approved_by,
        approval_reference=args.approval_reference,
    )

    try:
        authorized_plan = authorize_remediation(plan, approval, current)
    except (RemediationApprovalError, StaleRemediationPlanError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    applied = execute_compliance_write(ShopifyComplianceWriter(), authorized_plan, dry_run=False)
    if applied:
        print(f"\n✅ Written to Shopify. Approved by {args.approved_by} ({args.approval_reference}).")
    else:
        print("\nNo write performed.")


if __name__ == "__main__":
    main()
