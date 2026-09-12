from __future__ import annotations

from dataclasses import dataclass

from app.core.international_compliance.audit import ShopifyComplianceSnapshot
from app.core.international_compliance.persistence import PlannedComplianceWrite


class StaleRemediationPlanError(RuntimeError):
    pass


class RemediationApprovalError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class RemediationApproval:
    inventory_item_id: str
    classification_fingerprint: str
    approved_hs6: str
    approved_country_of_origin: str
    approved_weight_grams: float
    approved_by: str
    approval_reference: str

    def __post_init__(self) -> None:
        if not self.inventory_item_id.strip():
            raise ValueError("inventory_item_id is required")
        if not self.classification_fingerprint.strip():
            raise ValueError("classification_fingerprint is required")
        if len(self.approved_hs6) != 6 or not self.approved_hs6.isdigit():
            raise ValueError("approved_hs6 must be exactly six digits")
        coo = self.approved_country_of_origin
        if len(coo) != 2 or not coo.isalpha() or coo != coo.upper():
            raise ValueError("approved_country_of_origin must be uppercase ISO alpha-2")
        if self.approved_weight_grams <= 0:
            raise ValueError("approved_weight_grams must be positive")
        if not self.approved_by.strip():
            raise ValueError("approved_by is required")
        if not self.approval_reference.strip():
            raise ValueError("approval_reference is required")


def authorize_remediation(
    plan: PlannedComplianceWrite,
    approval: RemediationApproval,
    current: ShopifyComplianceSnapshot,
) -> PlannedComplianceWrite:
    """Authorize an exact, non-stale write plan after explicit human approval.

    This function performs no write. It guarantees that the approval describes
    the exact planned values and that Shopify has not changed since the plan was
    generated. Any drift requires a fresh audit and a new approval.
    """
    if approval.inventory_item_id != plan.inventory_item_id:
        raise RemediationApprovalError("approval inventory item does not match plan")
    if approval.classification_fingerprint != plan.classification_fingerprint:
        raise RemediationApprovalError("approval fingerprint does not match plan")
    if approval.approved_hs6 != plan.new_hs_code:
        raise RemediationApprovalError("approved HS code does not match plan")
    if approval.approved_country_of_origin != plan.new_country_of_origin:
        raise RemediationApprovalError("approved country of origin does not match plan")
    if approval.approved_weight_grams != plan.new_weight_grams:
        raise RemediationApprovalError("approved weight does not match plan")

    current_coo = (current.country_of_origin or "").upper() or None
    planned_old_coo = (plan.old_country_of_origin or "").upper() or None
    if (
        current.hs_code != plan.old_hs_code
        or current_coo != planned_old_coo
        or current.weight_grams != plan.old_weight_grams
    ):
        raise StaleRemediationPlanError(
            "Shopify compliance state changed after the remediation plan was created"
        )

    return plan
