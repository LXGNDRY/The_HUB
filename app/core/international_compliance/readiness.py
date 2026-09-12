from dataclasses import dataclass
from enum import Enum

from app.core.international_compliance.classifier import classify
from app.core.international_compliance.models import ComplianceInput, ReviewState


class InternationalReadiness(str, Enum):
    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class DestinationCapability:
    country_code: str
    supplier_shipping_supported: bool | None = None
    market_enabled: bool | None = None
    payment_supported: bool | None = None
    shipping_rate_available: bool | None = None
    duty_handling_supported: bool | None = None

    def __post_init__(self) -> None:
        if len(self.country_code) != 2 or not self.country_code.isalpha():
            raise ValueError("country_code must be ISO alpha-2")


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    status: InternationalReadiness
    reasons: tuple[str, ...]


def evaluate_international_readiness(
    item: ComplianceInput,
    destination: DestinationCapability,
) -> ReadinessResult:
    """Fail closed unless both product compliance and destination path are proven."""
    decision = classify(item)
    if decision.review_state is not ReviewState.READY:
        return ReadinessResult(
            status=InternationalReadiness.REVIEW_REQUIRED,
            reasons=("classification_not_ready", *decision.reasons),
        )

    product_failures: list[str] = []
    if item.weight_grams is None or item.weight_grams <= 0:
        product_failures.append("invalid_weight")
    if not (item.shopify_taxonomy or "").strip():
        product_failures.append("missing_shopify_taxonomy")
    if not item.requires_shipping:
        product_failures.append("physical_product_not_marked_for_shipping")
    if not item.taxable:
        product_failures.append("physical_product_not_taxable")
    if product_failures:
        return ReadinessResult(
            status=InternationalReadiness.REVIEW_REQUIRED,
            reasons=tuple(product_failures),
        )

    checks = {
        "supplier_shipping_supported": destination.supplier_shipping_supported,
        "market_enabled": destination.market_enabled,
        "payment_supported": destination.payment_supported,
        "shipping_rate_available": destination.shipping_rate_available,
        "duty_handling_supported": destination.duty_handling_supported,
    }
    blocked = tuple(f"destination_blocked:{name}" for name, value in checks.items() if value is False)
    if blocked:
        return ReadinessResult(status=InternationalReadiness.BLOCKED, reasons=blocked)

    unknown = tuple(f"destination_unverified:{name}" for name, value in checks.items() if value is None)
    if unknown:
        return ReadinessResult(
            status=InternationalReadiness.REVIEW_REQUIRED,
            reasons=unknown,
        )

    return ReadinessResult(
        status=InternationalReadiness.READY,
        reasons=(f"international_path_verified:{destination.country_code.upper()}",),
    )
