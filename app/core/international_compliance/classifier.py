from dataclasses import dataclass

from app.core.international_compliance.evidence import (
    detect_conflicts,
    has_verified_supplier_or_manufacturer_evidence,
)
from app.core.international_compliance.models import (
    ClassificationConfidence,
    ClassificationDecision,
    ComplianceInput,
    MaterialComponent,
    ReviewState,
)
from app.core.international_compliance.policy import missing_required_fields


@dataclass(frozen=True, slots=True)
class ClassificationRule:
    name: str
    hs6: str
    garment_types: frozenset[str]
    construction: str | None = None
    required_single_fiber: str | None = None

    def matches(self, item: ComplianceInput) -> bool:
        garment_type = (item.garment_type or "").strip().lower()
        if garment_type not in self.garment_types:
            return False
        if self.construction is not None:
            construction = (item.construction or "").strip().lower()
            if construction != self.construction:
                return False
        if self.required_single_fiber is None:
            return True
        return _is_single_fiber(item.materials, self.required_single_fiber)


RULE_VERSION = "v2.1.0"

_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        name="knit_cotton_tshirt_or_tank",
        hs6="610910",
        garment_types=frozenset({"t-shirt", "tshirt", "tee", "tank top", "tank"}),
        construction="knit",
        required_single_fiber="cotton",
    ),
    ClassificationRule(
        name="knit_cotton_sweater_sweatshirt_hoodie",
        hs6="611020",
        garment_types=frozenset({"hoodie", "sweatshirt", "crewneck", "sweater"}),
        construction="knit",
        required_single_fiber="cotton",
    ),
    ClassificationRule(
        name="sunglasses",
        hs6="900410",
        garment_types=frozenset({"sunglasses"}),
    ),
)


def _is_single_fiber(materials: tuple[MaterialComponent, ...], fiber: str) -> bool:
    return (
        len(materials) == 1
        and materials[0].fiber.strip().lower() == fiber.lower()
        and 99.0 <= materials[0].percentage <= 100.0
    )


def classify(item: ComplianceInput) -> ClassificationDecision:
    """Classify from normalized evidence only; never from title keywords."""
    conflicts = detect_conflicts(item.evidence)
    if conflicts:
        return ClassificationDecision(
            hs6=None,
            country_of_origin=None,
            confidence=ClassificationConfidence.UNKNOWN,
            review_state=ReviewState.REVIEW_REQUIRED,
            reasons=tuple(f"evidence_conflict:{conflict.field_name}" for conflict in conflicts),
            rule_version=RULE_VERSION,
            country_tariff_codes=item.country_tariff_codes,
        )

    missing = missing_required_fields(item)
    if missing:
        return ClassificationDecision(
            hs6=None,
            country_of_origin=None,
            confidence=ClassificationConfidence.UNKNOWN,
            review_state=ReviewState.REVIEW_REQUIRED,
            reasons=tuple(f"missing_required_field:{field_name}" for field_name in missing),
            rule_version=RULE_VERSION,
            country_tariff_codes=item.country_tariff_codes,
        )

    matched_rule = next((rule for rule in _RULES if rule.matches(item)), None)
    if matched_rule is None:
        return ClassificationDecision(
            hs6=None,
            country_of_origin=None,
            confidence=ClassificationConfidence.UNKNOWN,
            review_state=ReviewState.REVIEW_REQUIRED,
            reasons=("unsupported_or_ambiguous_classification",),
            rule_version=RULE_VERSION,
            country_tariff_codes=item.country_tariff_codes,
        )

    origin = (item.manufacturing_country or "").upper()
    origin_verified = has_verified_supplier_or_manufacturer_evidence(
        item.evidence,
        "manufacturing_country",
        origin,
    )
    if not origin_verified:
        return ClassificationDecision(
            hs6=matched_rule.hs6,
            country_of_origin=None,
            confidence=ClassificationConfidence.MEDIUM,
            review_state=ReviewState.REVIEW_REQUIRED,
            reasons=(
                f"matched_rule:{matched_rule.name}",
                "manufacturing_country_not_verified",
            ),
            rule_version=RULE_VERSION,
            country_tariff_codes=item.country_tariff_codes,
        )

    return ClassificationDecision(
        hs6=matched_rule.hs6,
        country_of_origin=origin,
        confidence=ClassificationConfidence.HIGH,
        review_state=ReviewState.READY,
        reasons=(f"matched_rule:{matched_rule.name}", "origin_evidence_verified"),
        rule_version=RULE_VERSION,
        country_tariff_codes=item.country_tariff_codes,
    )
