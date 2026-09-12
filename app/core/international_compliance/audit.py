from dataclasses import dataclass
from enum import Enum

from app.core.international_compliance.classifier import classify
from app.core.international_compliance.models import (
    ClassificationDecision,
    ComplianceInput,
    ReviewState,
)


class AuditStatus(str, Enum):
    VERIFIED_MATCH = "verified_match"
    LIKELY_MISMATCH = "likely_mismatch"
    MISSING = "missing"
    INSUFFICIENT_DATA = "insufficient_data"
    UNSUPPORTED_CATEGORY = "unsupported_category"
    MANUAL_OVERRIDE = "manual_override"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class ShopifyComplianceSnapshot:
    hs_code: str | None = None
    country_of_origin: str | None = None
    weight_grams: float | None = None
    taxonomy: str | None = None
    manual_override: bool = False


@dataclass(frozen=True, slots=True)
class ComplianceAuditResult:
    status: AuditStatus
    reasons: tuple[str, ...]
    expected_hs6: str | None
    current_hs: str | None
    expected_country_of_origin: str | None
    current_country_of_origin: str | None


def audit_compliance(
    item: ComplianceInput, current: ShopifyComplianceSnapshot
) -> ComplianceAuditResult:
    """Compare Shopify state with V2's evidence-backed classification, read-only."""
    decision = classify(item)

    if current.manual_override:
        return _result(AuditStatus.MANUAL_OVERRIDE, ("manual_override",), decision, current)

    if any(reason.startswith("evidence_conflict:") for reason in decision.reasons):
        return _result(AuditStatus.CONFLICT, decision.reasons, decision, current)

    if "unsupported_or_ambiguous_classification" in decision.reasons:
        return _result(AuditStatus.UNSUPPORTED_CATEGORY, decision.reasons, decision, current)

    if decision.review_state is not ReviewState.READY:
        return _result(AuditStatus.INSUFFICIENT_DATA, decision.reasons, decision, current)

    missing: list[str] = []
    if not (current.hs_code or "").strip():
        missing.append("hs_code")
    if not (current.country_of_origin or "").strip():
        missing.append("country_of_origin")
    if current.weight_grams is None or current.weight_grams <= 0:
        missing.append("weight_grams")
    if missing:
        return _result(
            AuditStatus.MISSING,
            tuple(f"missing_shopify_field:{field_name}" for field_name in missing),
            decision,
            current,
        )

    mismatches: list[str] = []
    if current.hs_code != decision.hs6:
        mismatches.append("hs_code")
    if current.country_of_origin.upper() != decision.country_of_origin:
        mismatches.append("country_of_origin")
    if mismatches:
        return _result(
            AuditStatus.LIKELY_MISMATCH,
            tuple(f"shopify_mismatch:{field_name}" for field_name in mismatches),
            decision,
            current,
        )

    return _result(AuditStatus.VERIFIED_MATCH, ("classification_matches",), decision, current)


def _result(
    status: AuditStatus,
    reasons: tuple[str, ...],
    decision: ClassificationDecision,
    current: ShopifyComplianceSnapshot,
) -> ComplianceAuditResult:
    return ComplianceAuditResult(
        status=status,
        reasons=reasons,
        expected_hs6=decision.hs6,
        current_hs=current.hs_code,
        expected_country_of_origin=decision.country_of_origin,
        current_country_of_origin=current.country_of_origin,
    )
