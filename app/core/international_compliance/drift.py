from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.core.international_compliance.ledger import ComplianceLedgerEntry


class DriftStatus(str, Enum):
    NEW = "new"
    UNCHANGED = "unchanged"
    COMPLIANCE_FACTS_CHANGED = "compliance_facts_changed"
    SHOPIFY_STATE_CHANGED = "shopify_state_changed"
    STATUS_CHANGED = "status_changed"


@dataclass(frozen=True, slots=True)
class ComplianceDriftResult:
    status: DriftStatus
    reasons: tuple[str, ...]


def detect_compliance_drift(
    previous: ComplianceLedgerEntry | None,
    current: ComplianceLedgerEntry,
) -> ComplianceDriftResult:
    """Compare immutable audit ledger entries without guessing why data changed."""
    if previous is None:
        return ComplianceDriftResult(DriftStatus.NEW, ("first_observation",))

    if previous.product_id != current.product_id or previous.variant_id != current.variant_id:
        raise ValueError("ledger entries must refer to the same product variant")

    if previous.fingerprint != current.fingerprint:
        return ComplianceDriftResult(
            DriftStatus.COMPLIANCE_FACTS_CHANGED,
            ("classification_fingerprint_changed",),
        )

    state_changes: list[str] = []
    if previous.current_hs != current.current_hs:
        state_changes.append("shopify_hs_changed")
    if previous.current_country_of_origin != current.current_country_of_origin:
        state_changes.append("shopify_country_of_origin_changed")
    if state_changes:
        return ComplianceDriftResult(
            DriftStatus.SHOPIFY_STATE_CHANGED,
            tuple(state_changes),
        )

    if previous.status != current.status:
        return ComplianceDriftResult(
            DriftStatus.STATUS_CHANGED,
            (f"audit_status:{previous.status}->{current.status}",),
        )

    return ComplianceDriftResult(DriftStatus.UNCHANGED, ("no_compliance_drift",))
