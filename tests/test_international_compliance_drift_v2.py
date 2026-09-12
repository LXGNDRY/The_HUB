import pytest

from app.core.international_compliance.drift import DriftStatus, detect_compliance_drift
from app.core.international_compliance.ledger import ComplianceLedgerEntry


def _entry(
    *,
    fingerprint: str = "fp-1",
    status: str = "verified_match",
    current_hs: str | None = "610910",
    current_coo: str | None = "CN",
) -> ComplianceLedgerEntry:
    return ComplianceLedgerEntry(
        product_id="p1",
        variant_id="v1",
        fingerprint=fingerprint,
        status=status,
        reasons=("classification_matches",),
        expected_hs6="610910",
        current_hs=current_hs,
        expected_country_of_origin="CN",
        current_country_of_origin=current_coo,
        recorded_at="2026-09-12T14:00:00+00:00",
    )


def test_first_observation_is_new() -> None:
    result = detect_compliance_drift(None, _entry())
    assert result.status is DriftStatus.NEW


def test_same_entry_is_unchanged() -> None:
    result = detect_compliance_drift(_entry(), _entry())
    assert result.status is DriftStatus.UNCHANGED


def test_fingerprint_change_has_priority() -> None:
    result = detect_compliance_drift(_entry(), _entry(fingerprint="fp-2"))
    assert result.status is DriftStatus.COMPLIANCE_FACTS_CHANGED


def test_shopify_state_change_is_detected() -> None:
    result = detect_compliance_drift(_entry(), _entry(current_hs="630790"))
    assert result.status is DriftStatus.SHOPIFY_STATE_CHANGED
    assert result.reasons == ("shopify_hs_changed",)


def test_status_change_is_detected_when_facts_and_shopify_state_are_same() -> None:
    result = detect_compliance_drift(_entry(), _entry(status="likely_mismatch"))
    assert result.status is DriftStatus.STATUS_CHANGED


def test_different_variant_is_rejected() -> None:
    current = ComplianceLedgerEntry(
        product_id="p1",
        variant_id="v2",
        fingerprint="fp-1",
        status="verified_match",
        reasons=(),
        expected_hs6="610910",
        current_hs="610910",
        expected_country_of_origin="CN",
        current_country_of_origin="CN",
        recorded_at="2026-09-12T15:00:00+00:00",
    )
    with pytest.raises(ValueError, match="same product variant"):
        detect_compliance_drift(_entry(), current)
