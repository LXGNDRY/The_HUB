import pytest

from app.core.international_compliance.models import ComplianceInput, ReviewState
from app.core.international_compliance.review import (
    ManualReviewResolution,
    apply_manual_review,
    reviewed_classification_is_current,
)


def _item(weight: float = 300) -> ComplianceInput:
    return ComplianceInput(
        product_id="p1",
        variant_id="v1",
        title="Reviewed item",
        supplier="podco",
        supplier_product_id="blank-1",
        product_family="apparel",
        garment_type="t-shirt",
        construction="knit",
        manufacturing_country="CN",
        weight_grams=weight,
        shopify_taxonomy="Apparel > Shirts",
    )


def test_manual_review_creates_verified_ready_decision() -> None:
    resolution = ManualReviewResolution(
        hs6="610910",
        country_of_origin="CN",
        reviewer="compliance@example.com",
        rationale="Verified against supplier specification and tariff source",
        evidence_reference="case:LB-1001",
        reviewed_at="2026-09-12T14:00:00+00:00",
    )

    reviewed = apply_manual_review(_item(), resolution)

    assert reviewed.decision.review_state is ReviewState.READY
    assert reviewed.decision.hs6 == "610910"
    assert reviewed.decision.country_of_origin == "CN"
    assert reviewed.decision.rule_version == "manual-review-v2"
    assert "manual_review_verified" in reviewed.decision.reasons
    assert reviewed_classification_is_current(_item(), reviewed) is True


def test_manual_review_becomes_stale_when_compliance_facts_change() -> None:
    resolution = ManualReviewResolution(
        hs6="610910",
        country_of_origin="CN",
        reviewer="reviewer",
        rationale="verified",
        evidence_reference="case:1",
        reviewed_at="2026-09-12T14:00:00+00:00",
    )
    reviewed = apply_manual_review(_item(weight=300), resolution)

    assert reviewed_classification_is_current(_item(weight=325), reviewed) is False


def test_manual_review_rejects_invalid_hs_code() -> None:
    with pytest.raises(ValueError, match="six digits"):
        ManualReviewResolution(
            hs6="61091",
            country_of_origin="CN",
            reviewer="reviewer",
            rationale="verified",
            evidence_reference="case:1",
            reviewed_at="2026-09-12T14:00:00+00:00",
        )
