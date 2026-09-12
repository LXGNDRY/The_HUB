from app.core.international_compliance.audit import ShopifyComplianceSnapshot
from app.core.international_compliance.models import (
    ComplianceEvidence,
    ComplianceInput,
    EvidenceSource,
    MaterialComponent,
)
from app.core.international_compliance.persistence import (
    execute_compliance_write,
    plan_compliance_write,
)


class _RecordingWriter:
    def __init__(self) -> None:
        self.plans = []

    def apply(self, plan) -> None:
        self.plans.append(plan)


def _item(*, verified_origin: bool = True) -> ComplianceInput:
    return ComplianceInput(
        product_id="p1",
        variant_id="v1",
        title="Tee",
        supplier="pod-a",
        supplier_product_id="blank-1",
        product_family="apparel",
        garment_type="t-shirt",
        construction="knit",
        materials=(MaterialComponent("cotton", 100),),
        manufacturing_country="CN",
        weight_grams=250,
        shopify_taxonomy="T-Shirts",
        evidence=(
            ComplianceEvidence(
                field_name="manufacturing_country",
                value="CN",
                source=EvidenceSource.SUPPLIER,
                source_reference="supplier-product-1",
                verified=verified_origin,
            ),
        ),
    )


def test_no_plan_when_classification_is_not_write_eligible() -> None:
    plan = plan_compliance_write(
        "gid://shopify/InventoryItem/1",
        _item(verified_origin=False),
        ShopifyComplianceSnapshot(),
    )
    assert plan is None


def test_plan_records_old_new_values_and_fingerprint() -> None:
    item = _item()
    plan = plan_compliance_write(
        "gid://shopify/InventoryItem/1",
        item,
        ShopifyComplianceSnapshot(
            hs_code="630790",
            country_of_origin="US",
            weight_grams=200,
        ),
    )
    assert plan is not None
    assert plan.old_hs_code == "630790"
    assert plan.new_hs_code == "610910"
    assert plan.old_country_of_origin == "US"
    assert plan.new_country_of_origin == "CN"
    assert plan.classification_fingerprint == item.fingerprint()


def test_idempotent_match_produces_no_write_plan() -> None:
    plan = plan_compliance_write(
        "gid://shopify/InventoryItem/1",
        _item(),
        ShopifyComplianceSnapshot(
            hs_code="610910",
            country_of_origin="CN",
            weight_grams=250,
        ),
    )
    assert plan is None


def test_execution_defaults_to_dry_run() -> None:
    plan = plan_compliance_write(
        "gid://shopify/InventoryItem/1",
        _item(),
        ShopifyComplianceSnapshot(),
    )
    assert plan is not None
    writer = _RecordingWriter()
    assert execute_compliance_write(writer, plan) is False
    assert writer.plans == []


def test_explicit_non_dry_run_calls_writer() -> None:
    plan = plan_compliance_write(
        "gid://shopify/InventoryItem/1",
        _item(),
        ShopifyComplianceSnapshot(),
    )
    assert plan is not None
    writer = _RecordingWriter()
    assert execute_compliance_write(writer, plan, dry_run=False) is True
    assert writer.plans == [plan]
