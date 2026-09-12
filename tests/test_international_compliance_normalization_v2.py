from app.core.international_compliance.models import (
    ComplianceEvidence,
    CountryTariffCode,
    EvidenceSource,
    MaterialComponent,
)
from app.core.international_compliance.normalization import (
    ShopifyProductFacts,
    normalize_compliance_input,
)
from app.core.international_compliance.suppliers.base import SupplierComplianceFacts


def test_supplier_physical_facts_override_shopify_without_guessing() -> None:
    shopify = ShopifyProductFacts(
        product_id="p1",
        variant_id="v1",
        title="Legendary Tee",
        shopify_taxonomy="Apparel > Shirts",
        requires_shipping=True,
        taxable=True,
        weight_grams=250,
        supplier="legacy",
        supplier_product_id="legacy-1",
        garment_type="shirt",
        construction=None,
        manufacturing_country="US",
        gender_category="men",
        intended_use="streetwear",
        subtype="short sleeve",
    )
    origin_evidence = ComplianceEvidence(
        field_name="manufacturing_country",
        value="CN",
        source=EvidenceSource.SUPPLIER,
        source_reference="supplier:blank-7",
        verified=True,
    )
    supplier = SupplierComplianceFacts(
        supplier="podco",
        supplier_product_id="blank-7",
        product_family="apparel",
        garment_type="t-shirt",
        construction="knit",
        materials=(MaterialComponent("cotton", 100),),
        manufacturing_country="cn",
        gender_category="unisex",
        intended_use="casual wear",
        subtype="crew neck",
        weight_grams=305,
        country_tariff_codes=(
            CountryTariffCode("US", "6109100012", "htsus:6109.10.0012"),
        ),
        evidence=(origin_evidence,),
    )

    normalized = normalize_compliance_input(shopify, supplier)

    assert normalized.supplier == "podco"
    assert normalized.supplier_product_id == "blank-7"
    assert normalized.garment_type == "t-shirt"
    assert normalized.construction == "knit"
    assert normalized.materials == (MaterialComponent("cotton", 100),)
    assert normalized.manufacturing_country == "CN"
    assert normalized.weight_grams == 305
    assert normalized.gender_category == "unisex"
    assert normalized.intended_use == "casual wear"
    assert normalized.subtype == "crew neck"
    assert normalized.country_tariff_codes == supplier.country_tariff_codes
    assert normalized.shopify_taxonomy == "Apparel > Shirts"
    assert normalized.evidence == (origin_evidence,)


def test_missing_supplier_facts_remain_missing() -> None:
    shopify = ShopifyProductFacts(
        product_id="p2",
        variant_id="v2",
        title="Unknown POD Item",
        shopify_taxonomy=None,
        requires_shipping=True,
        taxable=True,
        weight_grams=None,
    )

    normalized = normalize_compliance_input(shopify, None)

    assert normalized.supplier is None
    assert normalized.product_family is None
    assert normalized.garment_type is None
    assert normalized.construction is None
    assert normalized.materials == ()
    assert normalized.manufacturing_country is None
    assert normalized.weight_grams is None


def test_invalid_nonpositive_shopify_weight_normalizes_to_missing() -> None:
    shopify = ShopifyProductFacts(
        product_id="p3",
        variant_id="v3",
        title="Zero Weight",
        shopify_taxonomy="Apparel > Shirts",
        requires_shipping=True,
        taxable=True,
        weight_grams=0,
        supplier="podco",
    )

    normalized = normalize_compliance_input(shopify, None)
    assert normalized.weight_grams is None
