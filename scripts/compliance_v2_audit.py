#!/usr/bin/env python3
"""
compliance_v2_audit.py — Legendary Branding

Read-only automated audit: runs every live Shopify variant through
Compliance V2 (app/core/international_compliance/) and reports which are
READY to sell internationally vs REVIEW_REQUIRED, and why. Never writes to
Shopify — see compliance_v2_apply.py for the human-approval-gated write path.

Auth (Shopify): SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET, or SHOPIFY_ADMIN_TOKEN
                (same as modules/shopify.py's token cache)

Usage:
  python scripts/compliance_v2_audit.py
  python scripts/compliance_v2_audit.py --csv-out compliance_v2_report.csv
"""

import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from modules.international_compliance_runner import run_audit  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Compliance V2 catalog audit (read-only)")
    parser.add_argument("--csv-out", default="compliance_v2_report.csv", help="Path to write the per-variant CSV report")
    args = parser.parse_args()

    print()
    print("=" * 72)
    print("  COMPLIANCE V2 — CATALOG AUDIT (read-only)")
    print("=" * 72)
    print(f"  Generated: {datetime.now(timezone.utc).isoformat()}")
    print()
    print("  Fetching live Shopify catalog and evaluating every variant...")

    report = run_audit()

    print()
    for line in report.summary_lines():
        print(f"  {line}")

    with open(args.csv_out, "w") as f:
        f.write(report.to_csv())
    print()
    print(f"  Per-variant CSV written to: {args.csv_out}")

    if report.planned_writes:
        print()
        print("  ⚠  Variants with a fully evidence-verified plan awaiting approval:")
        for plan in report.planned_writes[:20]:
            print(
                f"    {plan.inventory_item_id}: "
                f"HS {plan.old_hs_code or '(none)'} -> {plan.new_hs_code}, "
                f"COO {plan.old_country_of_origin or '(none)'} -> {plan.new_country_of_origin}"
            )
        if len(report.planned_writes) > 20:
            print(f"    ... and {len(report.planned_writes) - 20} more")
        print()
        print("  Nothing has been written. Review the plan, then run:")
        print("    python scripts/compliance_v2_apply.py --inventory-item-id <id> "
              "--approved-by <name> --approval-reference <ref> --apply")

    print()
    print("=" * 72)
    print("  END OF REPORT")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
