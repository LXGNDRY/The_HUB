from dataclasses import dataclass
from typing import Protocol

from app.core.international_compliance.models import (
    ComplianceEvidence,
    CountryTariffCode,
    MaterialComponent,
)


@dataclass(frozen=True, slots=True)
class SupplierComplianceFacts:
    supplier: str
    supplier_product_id: str
    product_family: str | None = None
    garment_type: str | None = None
    construction: str | None = None
    materials: tuple[MaterialComponent, ...] = ()
    manufacturing_country: str | None = None
    gender_category: str | None = None
    intended_use: str | None = None
    subtype: str | None = None
    weight_grams: float | None = None
    supplier_hs6: str | None = None
    fulfillment_regions: tuple[str, ...] = ()
    evidence: tuple[ComplianceEvidence, ...] = ()
    country_tariff_codes: tuple[CountryTariffCode, ...] = ()


class SupplierEvidenceAdapter(Protocol):
    """Contract implemented by each POD supplier integration."""

    @property
    def supplier_name(self) -> str: ...

    def fetch_compliance_facts(self, supplier_product_id: str) -> SupplierComplianceFacts:
        """Return evidence-backed facts for one supplier product/blank."""
        ...
