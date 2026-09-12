import pytest

from app.core.international_compliance.classifier import classify
from app.core.international_compliance.evidence import (
    detect_conflicts,
    has_verified_supplier_or_manufacturer_evidence,
)
from app.core.international_compliance.models import (
    ClassificationConfidence,
    ClassificationDecision,
    ComplianceEvidence,
    ComplianceInput,
    CountryTariffCode,
    EvidenceSource,
    MaterialComponent,
    ReviewState,
)
from app.core.international_compliance.policy import (
    can_write_to_shopify,
    fail_closed_decision,
    missing_required_fields,
)
from app.core.international_compliance.suppliers.base import SupplierComplianceFacts


def _verified_origin(country: str) -> ComplianceEvidence:
    return ComplianceEvidence(
        field_name="manufacturing_country",
        value=country,
        source=EvidenceSource.SUPPLIER,
        source_reference="supplier-product-1",
        verified=True,
    )


def _complete_item(**overrides: object) -> ComplianceInput:
    values: dict[str, object] = {
        "product_id": "p1",
        "variant_id": "v1",
        "title": "Storefront title does not drive classification",
        "supplier": "pod-a",
        "supplier_product_id": "blank-1",
        "product_family": "apparel",
        "garment_type": "t-shirt",
        "construction": "knit",
        "materials": (MaterialComponent("cotton", 100),),
        "manufacturing_country": "CN",
        "weight_grams": 250,
        "evidence": (_verified_origin("CN"),),
    }
    values.update(overrides)
    return ComplianceInput(**values)


def test_material_percentages_must_sum_to_approximately_100() -> None:
    with pytest.raises(ValueError, match="material percentages"):
        ComplianceInput(
            product_id="p1",
            variant_id="v1",
            title="tee",
            materials=(MaterialComponent("cotton", 80),),
        )


def test_fingerprint_changes_when_classification_relevant_data_changes() -> None:
    base = _complete_item()
    changed = _complete_item(
        title="renamed storefront title",
        manufacturing_country="US",
        evidence=(_verified_origin("US"),),
    )
    assert base.fingerprint() != changed.fingerprint()


def test_country_tariff_codes_remain_distinct_from_base_hs6() -> None:
    item = _complete_item(
        intended_use="casual wear",
        subtype="short sleeve",
        gender_category="unisex",
        country_tariff_codes=(
            CountryTariffCode("US", "6109100012", "htsus:6109.10.0012"),
        ),
    )

    decision = classify(item)

    assert decision.hs6 == "610910"
    assert decision.hs6 != item.country_tariff_codes[0].code
    assert decision.country_tariff_codes == item.country_tariff_codes
    assert item.fingerprint() != _complete_item().fingerprint()


def test_country_tariff_code_requires_a_destination_specific_extension() -> None:
    with pytest.raises(ValueError, match="longer than HS6"):
        CountryTariffCode("US", "610910", "htsus:6109.10")


def test_fail_closed_never_guesses_hs_or_coo() -> None:
    item = ComplianceInput(product_id="p1", variant_id="v1", title="Unknown product")
    decision = fail_closed_decision(item)
    assert decision.hs6 is None
    assert decision.country_of_origin is None
    assert decision.review_state is ReviewState.REVIEW_REQUIRED
    assert decision.confidence is ClassificationConfidence.UNKNOWN
    assert "supplier" in missing_required_fields(item)
    assert can_write_to_shopify(decision) is False


def test_ready_decision_requires_verified_or_high_confidence() -> None:
    with pytest.raises(ValueError, match="verified/high confidence"):
        ClassificationDecision(
            hs6="610910",
            country_of_origin="CN",
            confidence=ClassificationConfidence.MEDIUM,
            review_state=ReviewState.READY,
        )


def test_verified_ready_decision_can_pass_write_gate() -> None:
    decision = ClassificationDecision(
        hs6="610910",
        country_of_origin="CN",
        confidence=ClassificationConfidence.VERIFIED,
        review_state=ReviewState.READY,
    )
    assert can_write_to_shopify(decision) is True


def test_conflicting_verified_evidence_is_detected() -> None:
    evidence = (
        _verified_origin("CN"),
        ComplianceEvidence(
            field_name="manufacturing_country",
            value="US",
            source=EvidenceSource.MANUFACTURER,
            source_reference="manufacturer-record-1",
            verified=True,
        ),
    )
    conflicts = detect_conflicts(evidence)
    assert len(conflicts) == 1
    assert conflicts[0].field_name == "manufacturing_country"
    assert conflicts[0].values == ("CN", "US")


def test_unverified_evidence_cannot_establish_origin() -> None:
    evidence = (
        ComplianceEvidence(
            field_name="manufacturing_country",
            value="CN",
            source=EvidenceSource.SUPPLIER,
            source_reference="supplier-product-1",
            verified=False,
        ),
    )
    assert (
        has_verified_supplier_or_manufacturer_evidence(
            evidence, "manufacturing_country", "CN"
        )
        is False
    )


def test_supplier_contract_preserves_source_facts_without_guessing() -> None:
    facts = SupplierComplianceFacts(
        supplier="pod-a",
        supplier_product_id="blank-42",
        garment_type="t-shirt",
        construction="knit",
        materials=(MaterialComponent("cotton", 100),),
        manufacturing_country=None,
        supplier_hs6=None,
    )
    assert facts.manufacturing_country is None
    assert facts.supplier_hs6 is None


def test_verified_cotton_knit_tshirt_is_ready() -> None:
    decision = classify(_complete_item())
    assert decision.hs6 == "610910"
    assert decision.country_of_origin == "CN"
    assert decision.review_state is ReviewState.READY
    assert decision.confidence is ClassificationConfidence.HIGH
    assert can_write_to_shopify(decision) is True


def test_unverified_origin_blocks_write_even_when_hs_rule_matches() -> None:
    item = _complete_item(
        evidence=(
            ComplianceEvidence(
                field_name="manufacturing_country",
                value="CN",
                source=EvidenceSource.SUPPLIER,
                source_reference="supplier-product-1",
                verified=False,
            ),
        )
    )
    decision = classify(item)
    assert decision.hs6 == "610910"
    assert decision.country_of_origin is None
    assert decision.review_state is ReviewState.REVIEW_REQUIRED
    assert can_write_to_shopify(decision) is False


def test_denim_jeans_do_not_fall_back_to_knit_pants_code() -> None:
    decision = classify(
        _complete_item(
            garment_type="jeans",
            construction="woven",
            materials=(MaterialComponent("cotton", 100),),
        )
    )
    assert decision.hs6 is None
    assert decision.review_state is ReviewState.REVIEW_REQUIRED
    assert "unsupported_or_ambiguous_classification" in decision.reasons


def test_unsupported_bag_does_not_fall_back_to_tshirt_code() -> None:
    decision = classify(
        _complete_item(
            product_family="bags",
            garment_type="backpack",
            construction="woven",
            materials=(MaterialComponent("polyester", 100),),
        )
    )
    assert decision.hs6 is None
    assert decision.review_state is ReviewState.REVIEW_REQUIRED
