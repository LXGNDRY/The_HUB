from dataclasses import dataclass, field

from app.core.international_compliance.suppliers.base import (
    SupplierComplianceFacts,
    SupplierEvidenceAdapter,
)


class UnknownSupplierError(LookupError):
    pass


class UnknownSupplierProductError(LookupError):
    pass


@dataclass(slots=True)
class SupplierRegistry:
    _adapters: dict[str, SupplierEvidenceAdapter] = field(default_factory=dict)

    def register(self, adapter: SupplierEvidenceAdapter) -> None:
        name = adapter.supplier_name.strip().lower()
        if not name:
            raise ValueError("supplier_name is required")
        self._adapters[name] = adapter

    def resolve(self, supplier_name: str) -> SupplierEvidenceAdapter:
        key = supplier_name.strip().lower()
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise UnknownSupplierError(supplier_name) from exc


@dataclass(frozen=True, slots=True)
class StaticSupplierEvidenceAdapter:
    """Evidence adapter for explicitly curated supplier facts.

    It never manufactures missing compliance attributes. Provider-specific API
    adapters can implement the same protocol later without changing the core.
    """

    supplier_name: str
    products: dict[str, SupplierComplianceFacts]

    def fetch_compliance_facts(self, supplier_product_id: str) -> SupplierComplianceFacts:
        try:
            return self.products[supplier_product_id]
        except KeyError as exc:
            raise UnknownSupplierProductError(supplier_product_id) from exc
