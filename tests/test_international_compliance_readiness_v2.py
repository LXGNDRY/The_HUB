from app.core.international_compliance.models import (
    ComplianceEvidence,
    ComplianceInput,
    EvidenceSource,
    MaterialComponent,
)
from app.core.international_compliance.readiness import (
    DestinationCapability,
    InternationalReadiness,
    evaluate_international_readiness,
)


def _item(**overrides: object) -> ComplianceInput:
    values: dict[str, object] = {
        "product_id": "p1",
        "variant_id": "v1",
        "title": "Tee",
        "supplier": "pod-a",
        "supplier_product_id": "blank-1",
        "product_family": "apparel",
        "garment_type": "t-shirt",
        "construction": "knit",
        "materials": (MaterialComponent("cotton", 100),),
        "manufacturing_country": "CN",
        "weight_grams": 250,
        "shopify_taxonomy": "T-Shirts",
        "requires_shipping": True,
        "taxable": True,
        "evidence": (
            ComplianceEvidence(
                field_name="manufacturing_country",
                value="CN",
                source=EvidenceSource.SUPPLIER,
                source_reference="supplier-product-1",
                verified=True,
            ),
        ),
    }
    values.update(overrides)
    return ComplianceInput(**values)


def _destination(**overrides: object) -> DestinationCapability:
    values: dict[str, object] = {
        "country_code": "CA",
        "supplier_shipping_supported": True,
        "market_enabled": True,
        "payment_supported": True,
        "shipping_rate_available": True,
        "duty_handling_supported": True,
    }
    values.update(overrides)
    return DestinationCapability(**values)


def test_fully_verified_path_is_ready() -> None:
    result = evaluate_international_readiness(_item(), _destination())
    assert result.status is InternationalReadiness.READY


def test_explicit_payment_failure_blocks_destination() -> None:
    result = evaluate_international_readiness(
        _item(), _destination(payment_supported=False)
    )
    assert result.status is InternationalReadiness.BLOCKED
    assert "destination_blocked:payment_supported" in result.reasons


def test_unknown_shipping_path_requires_review() -> None:
    result = evaluate_international_readiness(
        _item(), _destination(shipping_rate_available=None)
    )
    assert result.status is InternationalReadiness.REVIEW_REQUIRED
    assert "destination_unverified:shipping_rate_available" in result.reasons


def test_missing_taxonomy_requires_review() -> None:
    result = evaluate_international_readiness(
        _item(shopify_taxonomy=None), _destination()
    )
    assert result.status is InternationalReadiness.REVIEW_REQUIRED
    assert "missing_shopify_taxonomy" in result.reasons


def test_unclassified_product_cannot_be_international_ready() -> None:
    item = ComplianceInput(product_id="p1", variant_id="v1", title="Unknown")
    result = evaluate_international_readiness(item, _destination())
    assert result.status is InternationalReadiness.REVIEW_REQUIRED
    assert "classification_not_ready" in result.reasons
