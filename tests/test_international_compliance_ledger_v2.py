import json

from app.core.international_compliance.audit import (
    ShopifyComplianceSnapshot,
    audit_compliance,
)
from app.core.international_compliance.ledger import (
    ComplianceLedgerEntry,
    ledger_entries_to_jsonl,
)
from app.core.international_compliance.models import (
    ComplianceEvidence,
    ComplianceInput,
    EvidenceSource,
    MaterialComponent,
)


def _item() -> ComplianceInput:
    return ComplianceInput(
        product_id="p1",
        variant_id="v1",
        title="Verified tee",
        supplier="podco",
        supplier_product_id="blank-1",
        product_family="apparel",
        garment_type="t-shirt",
        construction="knit",
        materials=(MaterialComponent("cotton", 100),),
        manufacturing_country="CN",
        weight_grams=300,
        shopify_taxonomy="Apparel > Shirts",
        evidence=(
            ComplianceEvidence(
                field_name="manufacturing_country",
                value="CN",
                source=EvidenceSource.SUPPLIER,
                source_reference="supplier:blank-1",
                verified=True,
            ),
        ),
    )


def test_ledger_records_audit_and_fingerprint() -> None:
    item = _item()
    audit = audit_compliance(
        item,
        ShopifyComplianceSnapshot(
            hs_code="610910",
            country_of_origin="CN",
            weight_grams=300,
            taxonomy="Apparel > Shirts",
        ),
    )

    entry = ComplianceLedgerEntry.from_audit(
        item, audit, recorded_at="2026-09-12T14:00:00+00:00"
    )

    assert entry.fingerprint == item.fingerprint()
    assert entry.status == "verified_match"
    assert entry.expected_hs6 == "610910"


def test_jsonl_export_is_deterministic_and_parseable() -> None:
    item = _item()
    audit = audit_compliance(
        item,
        ShopifyComplianceSnapshot(
            hs_code="630790",
            country_of_origin="CN",
            weight_grams=300,
            taxonomy="Apparel > Shirts",
        ),
    )
    entry = ComplianceLedgerEntry.from_audit(
        item, audit, recorded_at="2026-09-12T14:00:00+00:00"
    )

    output = ledger_entries_to_jsonl([entry])
    parsed = json.loads(output)

    assert parsed["status"] == "likely_mismatch"
    assert parsed["reasons"] == ["shopify_mismatch:hs_code"]
    assert output.endswith("\n")


def test_empty_ledger_export_is_empty() -> None:
    assert ledger_entries_to_jsonl([]) == ""
