from __future__ import annotations

from dataclasses import dataclass

from app.core.international_compliance.audit import (
    ComplianceAuditResult,
    audit_compliance,
)
from app.core.international_compliance.classifier import classify
from app.core.international_compliance.ledger import ComplianceLedgerEntry
from app.core.international_compliance.models import (
    ClassificationDecision,
    ComplianceInput,
)
from app.core.international_compliance.normalization import (
    ShopifyProductFacts,
    normalize_compliance_input,
)
from app.core.international_compliance.readiness import (
    DestinationCapability,
    ReadinessResult,
    evaluate_international_readiness,
)
from app.core.international_compliance.shopify_catalog import ShopifyVariantRecord
from app.core.international_compliance.suppliers.base import SupplierComplianceFacts
from app.core.international_compliance.suppliers.registry import (
    SupplierRegistry,
    UnknownSupplierError,
    UnknownSupplierProductError,
)


@dataclass(frozen=True, slots=True)
class SupplierBinding:
    supplier_name: str
    supplier_product_id: str

    def __post_init__(self) -> None:
        if not self.supplier_name.strip():
            raise ValueError("supplier_name is required")
        if not self.supplier_product_id.strip():
            raise ValueError("supplier_product_id is required")


@dataclass(frozen=True, slots=True)
class ComplianceEvaluation:
    item: ComplianceInput
    supplier_facts: SupplierComplianceFacts | None
    decision: ClassificationDecision
    audit: ComplianceAuditResult
    readiness: tuple[tuple[str, ReadinessResult], ...]
    ledger_entry: ComplianceLedgerEntry
    orchestration_reasons: tuple[str, ...] = ()


def evaluate_variant(
    record: ShopifyVariantRecord,
    *,
    registry: SupplierRegistry,
    supplier_binding: SupplierBinding | None,
    destinations: tuple[DestinationCapability, ...] = (),
    recorded_at: str | None = None,
) -> ComplianceEvaluation:
    """Run one variant through the complete read-only V2 compliance pipeline.

    Supplier identity is explicit. The orchestrator never derives a supplier
    product identifier from a title, SKU, vendor string, or tag. If a binding is
    missing or cannot be resolved, supplier facts remain unavailable and the
    downstream classifier fails closed.
    """
    supplier_facts, orchestration_reasons = _resolve_supplier_facts(
        registry, supplier_binding
    )
    shopify = _shopify_facts(record, supplier_binding)
    item = normalize_compliance_input(shopify, supplier_facts)
    decision = classify(item)
    audit = audit_compliance(item, record.compliance)
    readiness = tuple(
        (
            destination.country_code.upper(),
            evaluate_international_readiness(item, destination),
        )
        for destination in destinations
    )
    ledger_entry = ComplianceLedgerEntry.from_audit(
        item, audit, recorded_at=recorded_at
    )
    return ComplianceEvaluation(
        item=item,
        supplier_facts=supplier_facts,
        decision=decision,
        audit=audit,
        readiness=readiness,
        ledger_entry=ledger_entry,
        orchestration_reasons=orchestration_reasons,
    )


def _resolve_supplier_facts(
    registry: SupplierRegistry,
    binding: SupplierBinding | None,
) -> tuple[SupplierComplianceFacts | None, tuple[str, ...]]:
    if binding is None:
        return None, ("supplier_binding_missing",)
    try:
        adapter = registry.resolve(binding.supplier_name)
        return adapter.fetch_compliance_facts(binding.supplier_product_id), ()
    except UnknownSupplierError:
        return None, ("supplier_unregistered",)
    except UnknownSupplierProductError:
        return None, ("supplier_product_unresolved",)


def _shopify_facts(
    record: ShopifyVariantRecord,
    binding: SupplierBinding | None,
) -> ShopifyProductFacts:
    return ShopifyProductFacts(
        product_id=record.product_id,
        variant_id=record.variant_id,
        title=record.product_title,
        shopify_taxonomy=record.taxonomy,
        requires_shipping=record.requires_shipping,
        taxable=record.taxable,
        weight_grams=record.compliance.weight_grams,
        supplier=(binding.supplier_name if binding else None),
        supplier_product_id=(binding.supplier_product_id if binding else None),
    )
