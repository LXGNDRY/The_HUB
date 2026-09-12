import pytest

from app.core.international_compliance.audit import ShopifyComplianceSnapshot
from app.core.international_compliance.persistence import PlannedComplianceWrite
from app.core.international_compliance.remediation import (
    RemediationApproval,
    RemediationApprovalError,
    StaleRemediationPlanError,
    authorize_remediation,
)


def _plan() -> PlannedComplianceWrite:
    return PlannedComplianceWrite(
        inventory_item_id="gid://shopify/InventoryItem/3",
        classification_fingerprint="fingerprint-1",
        old_hs_code="630790",
        new_hs_code="610910",
        old_country_of_origin="CN",
        new_country_of_origin="CN",
        old_weight_grams=250,
        new_weight_grams=300,
        rule_version="v2.1.0",
        reasons=("matched_rule:knit_cotton_tshirt_or_tank",),
    )


def _approval() -> RemediationApproval:
    return RemediationApproval(
        inventory_item_id="gid://shopify/InventoryItem/3",
        classification_fingerprint="fingerprint-1",
        approved_hs6="610910",
        approved_country_of_origin="CN",
        approved_weight_grams=300,
        approved_by="owner",
        approval_reference="review:LB-001",
    )


def test_exact_approval_and_unchanged_snapshot_authorize_plan() -> None:
    plan = _plan()
    authorized = authorize_remediation(
        plan,
        _approval(),
        ShopifyComplianceSnapshot(
            hs_code="630790",
            country_of_origin="CN",
            weight_grams=250,
        ),
    )

    assert authorized is plan


def test_approval_for_different_hs_code_is_rejected() -> None:
    approval = RemediationApproval(
        inventory_item_id="gid://shopify/InventoryItem/3",
        classification_fingerprint="fingerprint-1",
        approved_hs6="611020",
        approved_country_of_origin="CN",
        approved_weight_grams=300,
        approved_by="owner",
        approval_reference="review:LB-001",
    )

    with pytest.raises(RemediationApprovalError, match="HS code"):
        authorize_remediation(
            _plan(),
            approval,
            ShopifyComplianceSnapshot(
                hs_code="630790",
                country_of_origin="CN",
                weight_grams=250,
            ),
        )


def test_changed_shopify_state_invalidates_plan() -> None:
    with pytest.raises(StaleRemediationPlanError, match="changed"):
        authorize_remediation(
            _plan(),
            _approval(),
            ShopifyComplianceSnapshot(
                hs_code="610910",
                country_of_origin="CN",
                weight_grams=250,
            ),
        )
