"""
Tests for the automated (no-human-approval) write path added on top of
Compliance V2: modules/international_compliance_runner.py::apply_ready_plans().

Safety is entirely upstream (plan_compliance_write only ever produces a plan
for evidence-verified, high/verified-confidence classifications); these tests
cover the automation-specific behavior: a fresh state re-check immediately
before writing, and skip-not-force on drift.
"""

from unittest.mock import patch

from app.core.international_compliance.audit import ShopifyComplianceSnapshot
from app.core.international_compliance.persistence import PlannedComplianceWrite
from app.core.international_compliance.shopify_catalog import ShopifyVariantRecord
from modules.international_compliance_runner import AuditReport, apply_ready_plans


def _make_plan(**overrides):
    defaults = dict(
        inventory_item_id="gid://shopify/InventoryItem/1",
        classification_fingerprint="abc123",
        old_hs_code=None,
        new_hs_code="610910",
        old_country_of_origin=None,
        new_country_of_origin="US",
        old_weight_grams=None,
        new_weight_grams=180.0,
        rule_version="v2.1.0",
        reasons=("matched_rule:knit_cotton_tshirt_or_tank", "origin_evidence_verified"),
    )
    defaults.update(overrides)
    return PlannedComplianceWrite(**defaults)


def _make_record(compliance: ShopifyComplianceSnapshot) -> ShopifyVariantRecord:
    return ShopifyVariantRecord(
        product_id="gid://shopify/Product/1",
        product_title="Test Tee",
        product_status="ACTIVE",
        vendor="Legendary Branding",
        product_type="Shirts & Tops",
        taxonomy=None,
        tags=(),
        variant_id="gid://shopify/ProductVariant/2",
        variant_title="S",
        sku="SKU-1",
        taxable=True,
        available_for_sale=True,
        inventory_item_id="gid://shopify/InventoryItem/1",
        requires_shipping=True,
        compliance=compliance,
    )


class _FakeWriter:
    def __init__(self):
        self.applied_plans = []

    def apply(self, plan):
        self.applied_plans.append(plan)


def test_apply_ready_plans_writes_without_any_human_approval_fields():
    """No --approved-by/--approval-reference exist anywhere in this call path."""
    plan = _make_plan()
    report = AuditReport(
        total_variants=1, ready_count=1, review_required_count=0,
        reason_counts={}, planned_writes=(plan,), evaluations=(),
    )
    fresh_record = _make_record(
        ShopifyComplianceSnapshot(hs_code=None, country_of_origin=None, weight_grams=None, taxonomy=None)
    )
    writer = _FakeWriter()

    with patch(
        "modules.international_compliance_runner.fetch_variant_record_by_inventory_item",
        return_value=fresh_record,
    ):
        result = apply_ready_plans(report, writer=writer)

    assert len(result.applied) == 1
    assert len(result.skipped) == 0
    assert len(writer.applied_plans) == 1
    assert writer.applied_plans[0].new_hs_code == "610910"


def test_apply_ready_plans_skips_stale_plan_without_writing():
    """If Shopify's live state has drifted since the audit ran, skip — never force."""
    plan = _make_plan()
    report = AuditReport(
        total_variants=1, ready_count=1, review_required_count=0,
        reason_counts={}, planned_writes=(plan,), evaluations=(),
    )
    drifted_record = _make_record(
        ShopifyComplianceSnapshot(hs_code="999999", country_of_origin="CN", weight_grams=999, taxonomy=None)
    )
    writer = _FakeWriter()

    with patch(
        "modules.international_compliance_runner.fetch_variant_record_by_inventory_item",
        return_value=drifted_record,
    ):
        result = apply_ready_plans(report, writer=writer)

    assert len(result.applied) == 0
    assert len(result.skipped) == 1
    assert writer.applied_plans == []
    assert "changed" in result.skipped[0].error


def test_apply_ready_plans_continues_after_one_item_fails():
    """One bad plan must not stop the rest of the batch from being applied."""
    good_plan = _make_plan(inventory_item_id="gid://shopify/InventoryItem/1")
    bad_plan = _make_plan(inventory_item_id="gid://shopify/InventoryItem/999")
    report = AuditReport(
        total_variants=2, ready_count=2, review_required_count=0,
        reason_counts={}, planned_writes=(good_plan, bad_plan), evaluations=(),
    )
    fresh_record = _make_record(
        ShopifyComplianceSnapshot(hs_code=None, country_of_origin=None, weight_grams=None, taxonomy=None)
    )
    writer = _FakeWriter()

    def fake_fetch(inventory_item_id):
        if inventory_item_id == "gid://shopify/InventoryItem/999":
            raise LookupError("no longer exists")
        return fresh_record

    with patch(
        "modules.international_compliance_runner.fetch_variant_record_by_inventory_item",
        side_effect=fake_fetch,
    ):
        result = apply_ready_plans(report, writer=writer)

    assert len(result.applied) == 1
    assert len(result.skipped) == 1
    assert result.skipped[0].inventory_item_id == "gid://shopify/InventoryItem/999"
    assert len(writer.applied_plans) == 1
