from app.core.international_compliance.audit import ShopifyComplianceSnapshot
from app.core.international_compliance.lifecycle import (
    ComplianceEventAction,
    decide_event_action,
    evaluate_event_in_shadow,
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
        "title": "Original title",
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


def test_new_product_is_evaluated() -> None:
    assert decide_event_action(None, _item()) is ComplianceEventAction.EVALUATE


def test_same_compliance_fingerprint_is_noop() -> None:
    item = _item()
    assert (
        decide_event_action(item.fingerprint(), item)
        is ComplianceEventAction.NOOP
    )


def test_storefront_title_change_does_not_trigger_reclassification() -> None:
    previous = _item(title="Old title")
    updated = _item(title="New SEO title")
    assert previous.fingerprint() == updated.fingerprint()
    assert (
        decide_event_action(previous.fingerprint(), updated)
        is ComplianceEventAction.NOOP
    )


def test_origin_change_triggers_reclassification() -> None:
    previous = _item(manufacturing_country="CN")
    updated = _item(
        manufacturing_country="US",
        evidence=(
            ComplianceEvidence(
                field_name="manufacturing_country",
                value="US",
                source=EvidenceSource.SUPPLIER,
                source_reference="supplier-product-1",
                verified=True,
            ),
        ),
    )
    assert (
        decide_event_action(previous.fingerprint(), updated)
        is ComplianceEventAction.EVALUATE
    )


def test_shadow_evaluation_never_performs_write() -> None:
    item = _item()
    result = evaluate_event_in_shadow(
        None,
        item,
        ShopifyComplianceSnapshot(
            hs_code="630790",
            country_of_origin="US",
            weight_grams=200,
        ),
    )
    assert result.action is ComplianceEventAction.EVALUATE
    assert result.audit is not None
