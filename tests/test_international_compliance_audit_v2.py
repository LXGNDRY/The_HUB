from app.core.international_compliance.audit import (
    AuditStatus,
    ShopifyComplianceSnapshot,
    audit_compliance,
)
from app.core.international_compliance.models import (
    ComplianceEvidence,
    ComplianceInput,
    EvidenceSource,
    MaterialComponent,
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


def test_matching_shopify_record_is_verified() -> None:
    result = audit_compliance(
        _item(),
        ShopifyComplianceSnapshot(
            hs_code="610910",
            country_of_origin="CN",
            weight_grams=250,
            taxonomy="T-Shirts",
        ),
    )
    assert result.status is AuditStatus.VERIFIED_MATCH


def test_populated_but_wrong_hs_is_not_treated_as_complete() -> None:
    result = audit_compliance(
        _item(),
        ShopifyComplianceSnapshot(
            hs_code="630790",
            country_of_origin="CN",
            weight_grams=250,
            taxonomy="T-Shirts",
        ),
    )
    assert result.status is AuditStatus.LIKELY_MISMATCH
    assert "shopify_mismatch:hs_code" in result.reasons


def test_missing_shopify_hs_is_reported_missing() -> None:
    result = audit_compliance(
        _item(),
        ShopifyComplianceSnapshot(
            hs_code=None,
            country_of_origin="CN",
            weight_grams=250,
        ),
    )
    assert result.status is AuditStatus.MISSING
    assert "missing_shopify_field:hs_code" in result.reasons


def test_unsupported_product_stays_unsupported_instead_of_guessing() -> None:
    result = audit_compliance(
        _item(
            product_family="bags",
            garment_type="backpack",
            construction="woven",
            materials=(MaterialComponent("polyester", 100),),
        ),
        ShopifyComplianceSnapshot(
            hs_code="610910",
            country_of_origin="CN",
            weight_grams=400,
        ),
    )
    assert result.status is AuditStatus.UNSUPPORTED_CATEGORY
    assert result.expected_hs6 is None


def test_manual_override_is_preserved_for_review() -> None:
    result = audit_compliance(
        _item(),
        ShopifyComplianceSnapshot(
            hs_code="610910",
            country_of_origin="CN",
            weight_grams=250,
            manual_override=True,
        ),
    )
    assert result.status is AuditStatus.MANUAL_OVERRIDE


def test_incomplete_product_evidence_is_not_labeled_match() -> None:
    item = ComplianceInput(product_id="p1", variant_id="v1", title="Unknown")
    result = audit_compliance(
        item,
        ShopifyComplianceSnapshot(
            hs_code="610910",
            country_of_origin="CN",
            weight_grams=200,
        ),
    )
    assert result.status is AuditStatus.INSUFFICIENT_DATA
