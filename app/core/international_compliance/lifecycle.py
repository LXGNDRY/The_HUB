from dataclasses import dataclass
from enum import Enum

from app.core.international_compliance.audit import (
    ComplianceAuditResult,
    ShopifyComplianceSnapshot,
    audit_compliance,
)
from app.core.international_compliance.models import ComplianceInput


class ComplianceEventAction(str, Enum):
    NOOP = "noop"
    EVALUATE = "evaluate"


@dataclass(frozen=True, slots=True)
class ShadowEvaluation:
    action: ComplianceEventAction
    fingerprint: str
    audit: ComplianceAuditResult | None


def decide_event_action(
    previous_fingerprint: str | None,
    item: ComplianceInput,
) -> ComplianceEventAction:
    """Re-evaluate only when classification-relevant facts changed."""
    current_fingerprint = item.fingerprint()
    if previous_fingerprint == current_fingerprint:
        return ComplianceEventAction.NOOP
    return ComplianceEventAction.EVALUATE


def evaluate_event_in_shadow(
    previous_fingerprint: str | None,
    item: ComplianceInput,
    current: ShopifyComplianceSnapshot,
) -> ShadowEvaluation:
    """Observe product events without performing any Shopify mutation."""
    fingerprint = item.fingerprint()
    action = decide_event_action(previous_fingerprint, item)
    if action is ComplianceEventAction.NOOP:
        return ShadowEvaluation(action=action, fingerprint=fingerprint, audit=None)
    return ShadowEvaluation(
        action=action,
        fingerprint=fingerprint,
        audit=audit_compliance(item, current),
    )
