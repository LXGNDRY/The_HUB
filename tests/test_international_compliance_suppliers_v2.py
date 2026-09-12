import pytest

from app.core.international_compliance.suppliers.base import SupplierComplianceFacts
from app.core.international_compliance.suppliers.registry import (
    StaticSupplierEvidenceAdapter,
    SupplierRegistry,
    UnknownSupplierError,
    UnknownSupplierProductError,
)


def test_registry_resolves_supplier_case_insensitively() -> None:
    adapter = StaticSupplierEvidenceAdapter(
        supplier_name="POD-A",
        products={
            "blank-1": SupplierComplianceFacts(
                supplier="POD-A",
                supplier_product_id="blank-1",
            )
        },
    )
    registry = SupplierRegistry()
    registry.register(adapter)
    assert registry.resolve("pod-a") is adapter


def test_unknown_supplier_fails_closed() -> None:
    registry = SupplierRegistry()
    with pytest.raises(UnknownSupplierError):
        registry.resolve("missing-provider")


def test_unknown_supplier_product_fails_closed() -> None:
    adapter = StaticSupplierEvidenceAdapter(supplier_name="POD-A", products={})
    with pytest.raises(UnknownSupplierProductError):
        adapter.fetch_compliance_facts("unknown-blank")


def test_static_adapter_preserves_missing_facts() -> None:
    facts = SupplierComplianceFacts(
        supplier="POD-A",
        supplier_product_id="blank-1",
        manufacturing_country=None,
        supplier_hs6=None,
    )
    adapter = StaticSupplierEvidenceAdapter(
        supplier_name="POD-A",
        products={"blank-1": facts},
    )
    resolved = adapter.fetch_compliance_facts("blank-1")
    assert resolved.manufacturing_country is None
    assert resolved.supplier_hs6 is None
