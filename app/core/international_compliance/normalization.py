from __future__ import annotations

from dataclasses import dataclass

from app.core.international_compliance.models import (
    ComplianceEvidence,
    ComplianceInput,
    CountryTariffCode,
    MaterialComponent,
)
from app.core.international_compliance.suppliers.base import SupplierComplianceFacts


@dataclass(frozen=True, slots=True)
class ShopifyProductFacts:
    product_id: str
    variant_id: str
    title: str
    shopify_taxonomy: str | None
    requires_shipping: bool
    taxable: bool
    weight_grams: float | None
    supplier: str | None = None
    supplier_product_id: str | None = None
    product_family: str | None = None
    garment_type: str | None = None
    construction: str | None = None
    materials: tuple[MaterialComponent, ...] = ()
    manufacturing_country: str | None = None
    gender_category: str | None = None
    intended_use: str | None = None
    subtype: str | None = None
    evidence: tuple[ComplianceEvidence, ...] = ()
    country_tariff_codes: tuple[CountryTariffCode, ...] = ()


def _prefer_supplier_text(shopify_value: str | None, supplier_value: str | None) -> str | None:
    supplier_clean = (supplier_value or "").strip()
    if supplier_clean:
        return supplier_clean
    shopify_clean = (shopify_value or "").strip()
    return shopify_clean or None


def _prefer_supplier_weight(
    shopify_weight: float | None, supplier_weight: float | None
) -> float | None:
    if supplier_weight is not None and supplier_weight > 0:
        return supplier_weight
    if shopify_weight is not None and shopify_weight > 0:
        return shopify_weight
    return None


def normalize_compliance_input(
    shopify: ShopifyProductFacts,
    supplier: SupplierComplianceFacts | None,
) -> ComplianceInput:
    """Build one canonical compliance input without inventing missing facts.

    Supplier/manufacturer facts take precedence for customs-relevant physical
    attributes. Shopify remains authoritative for commerce flags/taxonomy. Missing
    values remain missing so the classifier can fail closed.
    """
    if supplier is not None:
        supplier_name = supplier.supplier.strip() or None
        supplier_product_id = supplier.supplier_product_id.strip() or None
        product_family = _prefer_supplier_text(shopify.product_family, supplier.product_family)
        garment_type = _prefer_supplier_text(shopify.garment_type, supplier.garment_type)
        construction = _prefer_supplier_text(shopify.construction, supplier.construction)
        materials = supplier.materials or shopify.materials
        manufacturing_country = _prefer_supplier_text(
            shopify.manufacturing_country, supplier.manufacturing_country
        )
        gender_category = _prefer_supplier_text(
            shopify.gender_category, supplier.gender_category
        )
        intended_use = _prefer_supplier_text(shopify.intended_use, supplier.intended_use)
        subtype = _prefer_supplier_text(shopify.subtype, supplier.subtype)
        weight_grams = _prefer_supplier_weight(shopify.weight_grams, supplier.weight_grams)
        evidence = (*shopify.evidence, *supplier.evidence)
        country_tariff_codes = supplier.country_tariff_codes or shopify.country_tariff_codes
    else:
        supplier_name = (shopify.supplier or "").strip() or None
        supplier_product_id = (shopify.supplier_product_id or "").strip() or None
        product_family = (shopify.product_family or "").strip() or None
        garment_type = (shopify.garment_type or "").strip() or None
        construction = (shopify.construction or "").strip() or None
        materials = shopify.materials
        manufacturing_country = (shopify.manufacturing_country or "").strip() or None
        gender_category = (shopify.gender_category or "").strip() or None
        intended_use = (shopify.intended_use or "").strip() or None
        subtype = (shopify.subtype or "").strip() or None
        weight_grams = _prefer_supplier_weight(shopify.weight_grams, None)
        evidence = shopify.evidence
        country_tariff_codes = shopify.country_tariff_codes

    return ComplianceInput(
        product_id=shopify.product_id,
        variant_id=shopify.variant_id,
        title=shopify.title,
        supplier=supplier_name,
        supplier_product_id=supplier_product_id,
        product_family=product_family,
        garment_type=garment_type,
        construction=construction,
        materials=materials,
        manufacturing_country=(manufacturing_country.upper() if manufacturing_country else None),
        gender_category=gender_category,
        intended_use=intended_use,
        subtype=subtype,
        weight_grams=weight_grams,
        shopify_taxonomy=(shopify.shopify_taxonomy or "").strip() or None,
        requires_shipping=shopify.requires_shipping,
        taxable=shopify.taxable,
        evidence=tuple(evidence),
        country_tariff_codes=tuple(country_tariff_codes),
    )
