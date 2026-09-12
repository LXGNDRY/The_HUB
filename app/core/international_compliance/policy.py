from app.core.international_compliance.models import (
    ClassificationConfidence,
    ClassificationDecision,
    ComplianceInput,
    ReviewState,
)

_REQUIRED_CLASSIFICATION_FIELDS = (
    "supplier",
    "product_family",
    "garment_type",
    "construction",
    "materials",
    "manufacturing_country",
    "weight_grams",
)


def missing_required_fields(item: ComplianceInput) -> tuple[str, ...]:
    missing: list[str] = []
    for field_name in _REQUIRED_CLASSIFICATION_FIELDS:
        value = getattr(item, field_name)
        if value in (None, "", ()):
            missing.append(field_name)
    return tuple(missing)


def fail_closed_decision(item: ComplianceInput) -> ClassificationDecision:
    """Return a non-writing decision until a classifier proves readiness.

    V2 has no generic HS or COO fallback. Missing or incomplete evidence is a
    review condition, never permission to invent a customs value.
    """
    missing = missing_required_fields(item)
    reasons = (
        tuple(f"missing_required_field:{field_name}" for field_name in missing)
        if missing
        else ("classification_not_yet_verified",)
    )
    return ClassificationDecision(
        hs6=None,
        country_of_origin=None,
        confidence=ClassificationConfidence.UNKNOWN,
        review_state=ReviewState.REVIEW_REQUIRED,
        reasons=reasons,
    )


def can_write_to_shopify(decision: ClassificationDecision) -> bool:
    """Central write gate used by future Shopify persistence adapters."""
    return (
        decision.review_state is ReviewState.READY
        and decision.hs6 is not None
        and decision.country_of_origin is not None
        and decision.confidence
        in {ClassificationConfidence.VERIFIED, ClassificationConfidence.HIGH}
    )
