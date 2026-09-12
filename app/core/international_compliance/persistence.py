from dataclasses import dataclass
from typing import Protocol

from app.core.international_compliance.audit import ShopifyComplianceSnapshot
from app.core.international_compliance.classifier import classify
from app.core.international_compliance.models import ComplianceInput
from app.core.international_compliance.policy import can_write_to_shopify


@dataclass(frozen=True, slots=True)
class PlannedComplianceWrite:
    inventory_item_id: str
    classification_fingerprint: str
    old_hs_code: str | None
    new_hs_code: str
    old_country_of_origin: str | None
    new_country_of_origin: str
    old_weight_grams: float | None
    new_weight_grams: float
    rule_version: str
    reasons: tuple[str, ...]


class ComplianceWriter(Protocol):
    def apply(self, plan: PlannedComplianceWrite) -> None:
        """Persist an already-authorized plan to the commerce platform."""
        ...


def plan_compliance_write(
    inventory_item_id: str,
    item: ComplianceInput,
    current: ShopifyComplianceSnapshot,
) -> PlannedComplianceWrite | None:
    """Plan only evidence-backed changes; never mutate Shopify directly."""
    if not inventory_item_id.strip():
        raise ValueError("inventory_item_id is required")

    decision = classify(item)
    if not can_write_to_shopify(decision):
        return None
    if item.weight_grams is None or item.weight_grams <= 0:
        return None

    desired_hs = decision.hs6
    desired_coo = decision.country_of_origin
    if desired_hs is None or desired_coo is None:
        return None

    no_changes = (
        current.hs_code == desired_hs
        and (current.country_of_origin or "").upper() == desired_coo
        and current.weight_grams == item.weight_grams
    )
    if no_changes:
        return None

    return PlannedComplianceWrite(
        inventory_item_id=inventory_item_id,
        classification_fingerprint=item.fingerprint(),
        old_hs_code=current.hs_code,
        new_hs_code=desired_hs,
        old_country_of_origin=current.country_of_origin,
        new_country_of_origin=desired_coo,
        old_weight_grams=current.weight_grams,
        new_weight_grams=item.weight_grams,
        rule_version=decision.rule_version,
        reasons=decision.reasons,
    )


def execute_compliance_write(
    writer: ComplianceWriter,
    plan: PlannedComplianceWrite,
    *,
    dry_run: bool = True,
) -> bool:
    """Execute only when an explicit caller disables the safe dry-run default."""
    if dry_run:
        return False
    writer.apply(plan)
    return True
