from app.core.international_compliance.audit import (
    AuditStatus,
    ShopifyComplianceSnapshot,
)
from app.core.international_compliance.models import (
    ComplianceEvidence,
    EvidenceSource,
    MaterialComponent,
    ReviewState,
)
from app.core.international_compliance.orchestrator import (
    SupplierBinding,
    evaluate_variant,
)
from app.core.international_compliance.readiness import (
    DestinationCapability,
    InternationalReadiness,
)
from app.core.international_compliance.shopify_catalog import ShopifyVariantRecord
from app.core.international_compliance.suppliers.base import SupplierComplianceFacts
from app.core.international_compliance.suppliers.registry import (
    StaticSupplierEvidenceAdapter,
    SupplierRegistry,
)


def _record() -> ShopifyVariantRecord:
    return ShopifyVariantRecord(
        product_id="gid://shopify/Product/1",
        product_title="Legendary Heavyweight Tee",
        product_status="ACTIVE",
        vendor="Legendary Branding",
        product_type="Shirts & Tops",
        taxonomy="Apparel & Accessories > Clothing > Shirts & Tops",
        tags=(),
        variant_id="gid://shopify/ProductVariant/2",
        variant_title="Black / M",
        sku="TEE-BLK-M",
        taxable=True,
        available_for_sale=True,
        inventory_item_id="gid://shopify/InventoryItem/3",
        requires_shipping=True,
        compliance=ShopifyComplianceSnapshot(
            hs_code="610910",
            country_of_origin="CN",
            weight_grams=300,
            taxonomy="Apparel & Accessories > Clothing > Shirts & Tops",
        ),
    )


def _registry() -> SupplierRegistry:
    evidence = ComplianceEvidence(
        field_name="manufacturing_country",
        value="CN",
        source=EvidenceSource.SUPPLIER,
        source_reference="podco:blank-7",
        verified=True,
    )
    facts = SupplierComplianceFacts(
        supplier="podco",
        supplier_product_id="blank-7",
        product_family="apparel",
        garment_type="t-shirt",
        construction="knit",
        materials=(MaterialComponent("cotton", 100),),
        manufacturing_country="CN",
        weight_grams=300,
        evidence=(evidence,),
    )
    registry = SupplierRegistry()
    registry.register(
        StaticSupplierEvidenceAdapter(supplier_name="podco", products={"blank-7": facts})
    )
    return registry


def test_full_read_only_pipeline_reaches_verified_match_and_ready_destination() -> None:
    result = evaluate_variant(
        _record(),
        registry=_registry(),
        supplier_binding=SupplierBinding("podco", "blank-7"),
        destinations=(
            DestinationCapability(
                country_code="CA",
                supplier_shipping_supported=True,
                market_enabled=True,
                payment_supported=True,
                shipping_rate_available=True,
                duty_handling_supported=True,
            ),
        ),
        recorded_at="2026-09-12T14:00:00+00:00",
    )

    assert result.orchestration_reasons == ()
    assert result.decision.review_state is ReviewState.READY
    assert result.audit.status is AuditStatus.VERIFIED_MATCH
    assert result.readiness[0][0] == "CA"
    assert result.readiness[0][1].status is InternationalReadiness.READY
    assert result.ledger_entry.status == "verified_match"


def test_missing_supplier_binding_fails_closed_without_guessing() -> None:
    result = evaluate_variant(
        _record(),
        registry=_registry(),
        supplier_binding=None,
        recorded_at="2026-09-12T14:00:00+00:00",
    )

    assert result.supplier_facts is None
    assert result.orchestration_reasons == ("supplier_binding_missing",)
    assert result.decision.review_state is ReviewState.REVIEW_REQUIRED
    assert result.audit.status is AuditStatus.INSUFFICIENT_DATA
    assert result.item.garment_type is None
    assert result.item.manufacturing_country is None


def test_unknown_supplier_product_fails_closed() -> None:
    result = evaluate_variant(
        _record(),
        registry=_registry(),
        supplier_binding=SupplierBinding("podco", "missing-blank"),
        recorded_at="2026-09-12T14:00:00+00:00",
    )

    assert result.supplier_facts is None
    assert result.orchestration_reasons == ("supplier_product_unresolved",)
    assert result.decision.review_state is ReviewState.REVIEW_REQUIRED
    assert result.audit.status is AuditStatus.INSUFFICIENT_DATA
