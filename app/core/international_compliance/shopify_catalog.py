from dataclasses import dataclass

from app.core.international_compliance.audit import (
    ShopifyComplianceSnapshot,
)

_WEIGHT_TO_GRAMS = {
    "GRAMS": 1.0,
    "KILOGRAMS": 1000.0,
    "OUNCES": 28.349523125,
    "POUNDS": 453.59237,
}


@dataclass(frozen=True, slots=True)
class ShopifyVariantRecord:
    product_id: str
    product_title: str
    product_status: str
    vendor: str
    product_type: str
    taxonomy: str | None
    tags: tuple[str, ...]
    variant_id: str
    variant_title: str
    sku: str | None
    taxable: bool
    available_for_sale: bool
    inventory_item_id: str
    requires_shipping: bool
    compliance: ShopifyComplianceSnapshot
    printful_catalog_product_id: str | None = None
    variant_color: str | None = None


def weight_to_grams(value: float | None, unit: str | None) -> float | None:
    if value is None or unit is None:
        return None
    normalized = unit.strip().upper()
    multiplier = _WEIGHT_TO_GRAMS.get(normalized)
    if multiplier is None:
        raise ValueError(f"unsupported weight unit: {unit}")
    numeric = float(value)
    if numeric <= 0:
        return None
    return numeric * multiplier


def parse_product_node(product: dict) -> tuple[ShopifyVariantRecord, ...]:
    """Normalize a Shopify product response without inferring compliance facts."""
    category = product.get("category") or {}
    taxonomy = category.get("fullName") or category.get("name") or None
    tags = product.get("tags") or []
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]

    printful_metafield = product.get("printfulSyncMetafield") or {}
    printful_catalog_product_id = printful_metafield.get("value") or None

    records: list[ShopifyVariantRecord] = []
    variants = ((product.get("variants") or {}).get("nodes") or [])
    for variant in variants:
        inventory = variant.get("inventoryItem") or {}
        measurement = inventory.get("measurement") or {}
        weight = measurement.get("weight") or {}
        selected_options = variant.get("selectedOptions") or []
        variant_color = next(
            (
                str(option.get("value") or "").strip() or None
                for option in selected_options
                if str(option.get("name") or "").strip().lower() == "color"
            ),
            None,
        )
        records.append(
            ShopifyVariantRecord(
                product_id=str(product.get("id") or ""),
                product_title=str(product.get("title") or ""),
                product_status=str(product.get("status") or ""),
                vendor=str(product.get("vendor") or ""),
                product_type=str(product.get("productType") or ""),
                taxonomy=taxonomy,
                tags=tuple(str(tag) for tag in tags),
                variant_id=str(variant.get("id") or ""),
                variant_title=str(variant.get("title") or ""),
                sku=variant.get("sku") or None,
                taxable=bool(variant.get("taxable", False)),
                available_for_sale=bool(variant.get("availableForSale", False)),
                inventory_item_id=str(inventory.get("id") or ""),
                requires_shipping=bool(inventory.get("requiresShipping", False)),
                compliance=ShopifyComplianceSnapshot(
                    hs_code=inventory.get("harmonizedSystemCode") or None,
                    country_of_origin=inventory.get("countryCodeOfOrigin") or None,
                    weight_grams=weight_to_grams(weight.get("value"), weight.get("unit")),
                    taxonomy=taxonomy,
                ),
                printful_catalog_product_id=printful_catalog_product_id,
                variant_color=variant_color,
            )
        )
    return tuple(records)
