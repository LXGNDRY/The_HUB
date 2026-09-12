from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from typing import Any


class EvidenceSource(str, Enum):
    SHOPIFY = "shopify"
    SUPPLIER = "supplier"
    MANUFACTURER = "manufacturer"
    AUTHORITATIVE_TARIFF = "authoritative_tariff"
    MANUAL_VERIFICATION = "manual_verification"


class ClassificationConfidence(str, Enum):
    VERIFIED = "verified"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ReviewState(str, Enum):
    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class MaterialComponent:
    fiber: str
    percentage: float

    def __post_init__(self) -> None:
        if not self.fiber.strip():
            raise ValueError("fiber must be non-empty")
        if not 0 < self.percentage <= 100:
            raise ValueError("percentage must be within (0, 100]")


@dataclass(frozen=True, slots=True)
class CountryTariffCode:
    """A destination-specific tariff code, deliberately separate from base HS6."""

    country_code: str
    code: str
    source_reference: str

    def __post_init__(self) -> None:
        if len(self.country_code) != 2 or not self.country_code.isalpha():
            raise ValueError("country_code must be ISO alpha-2")
        if not self.code.isdigit() or len(self.code) <= 6:
            raise ValueError("country tariff code must be numeric and longer than HS6")
        if not self.source_reference.strip():
            raise ValueError("source_reference must be non-empty")


@dataclass(frozen=True, slots=True)
class ComplianceEvidence:
    field_name: str
    value: str
    source: EvidenceSource
    source_reference: str
    verified: bool = False

    def __post_init__(self) -> None:
        if not self.field_name.strip():
            raise ValueError("field_name must be non-empty")
        if not self.value.strip():
            raise ValueError("value must be non-empty")
        if not self.source_reference.strip():
            raise ValueError("source_reference must be non-empty")


@dataclass(frozen=True, slots=True)
class ComplianceInput:
    product_id: str
    variant_id: str
    title: str
    supplier: str | None = None
    supplier_product_id: str | None = None
    product_family: str | None = None
    garment_type: str | None = None
    construction: str | None = None
    materials: tuple[MaterialComponent, ...] = ()
    manufacturing_country: str | None = None
    gender_category: str | None = None
    intended_use: str | None = None
    subtype: str | None = None
    weight_grams: float | None = None
    shopify_taxonomy: str | None = None
    requires_shipping: bool = True
    taxable: bool = True
    evidence: tuple[ComplianceEvidence, ...] = ()
    country_tariff_codes: tuple[CountryTariffCode, ...] = ()

    def __post_init__(self) -> None:
        if not self.product_id.strip() or not self.variant_id.strip():
            raise ValueError("product_id and variant_id are required")
        if self.weight_grams is not None and self.weight_grams <= 0:
            raise ValueError("weight_grams must be positive when supplied")
        if self.materials:
            total = sum(component.percentage for component in self.materials)
            if not 99.0 <= total <= 101.0:
                raise ValueError("material percentages must total approximately 100")

    def fingerprint(self) -> str:
        """Stable hash of fields that can alter customs classification/readiness."""
        payload: dict[str, Any] = {
            "supplier": self.supplier,
            "supplier_product_id": self.supplier_product_id,
            "product_family": self.product_family,
            "garment_type": self.garment_type,
            "construction": self.construction,
            "materials": [
                {"fiber": component.fiber.lower(), "percentage": component.percentage}
                for component in self.materials
            ],
            "manufacturing_country": self.manufacturing_country,
            "gender_category": self.gender_category,
            "intended_use": self.intended_use,
            "subtype": self.subtype,
            "weight_grams": self.weight_grams,
            "shopify_taxonomy": self.shopify_taxonomy,
            "requires_shipping": self.requires_shipping,
            "taxable": self.taxable,
            "country_tariff_codes": [
                {
                    "country_code": code.country_code.upper(),
                    "code": code.code,
                    "source_reference": code.source_reference,
                }
                for code in sorted(
                    self.country_tariff_codes,
                    key=lambda code: (code.country_code.upper(), code.code),
                )
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ClassificationDecision:
    hs6: str | None
    country_of_origin: str | None
    confidence: ClassificationConfidence
    review_state: ReviewState
    reasons: tuple[str, ...] = ()
    rule_version: str = "v2.0.0"
    country_tariff_codes: tuple[CountryTariffCode, ...] = ()

    def __post_init__(self) -> None:
        if self.hs6 is not None and (len(self.hs6) != 6 or not self.hs6.isdigit()):
            raise ValueError("hs6 must be exactly six digits")
        if self.country_of_origin is not None:
            code = self.country_of_origin
            if len(code) != 2 or not code.isalpha() or code != code.upper():
                raise ValueError("country_of_origin must be an uppercase ISO alpha-2 code")
        if self.review_state is ReviewState.READY:
            if self.hs6 is None or self.country_of_origin is None:
                raise ValueError("READY decisions require both HS6 and COO")
            if self.confidence not in {
                ClassificationConfidence.VERIFIED,
                ClassificationConfidence.HIGH,
            }:
                raise ValueError("READY decisions require verified/high confidence")


@dataclass(frozen=True, slots=True)
class ComplianceRecord:
    input: ComplianceInput
    decision: ClassificationDecision
    classification_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "classification_fingerprint", self.input.fingerprint())
