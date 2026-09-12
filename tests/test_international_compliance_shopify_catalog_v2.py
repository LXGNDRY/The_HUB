import pytest

from app.core.international_compliance.shopify_catalog import (
    parse_product_node,
    weight_to_grams,
)


def _product_node(**inventory_overrides: object) -> dict:
    inventory = {
        "id": "gid://shopify/InventoryItem/1",
        "requiresShipping": True,
        "countryCodeOfOrigin": "CN",
        "harmonizedSystemCode": "610910",
        "measurement": {"weight": {"value": 0.25, "unit": "KILOGRAMS"}},
    }
    inventory.update(inventory_overrides)
    return {
        "id": "gid://shopify/Product/1",
        "title": "Legendary Tee",
        "status": "ACTIVE",
        "vendor": "POD Supplier",
        "productType": "Shirts & Tops",
        "tags": ["streetwear", "pod"],
        "category": {"id": "gid://shopify/TaxonomyCategory/1", "name": "T-Shirts", "fullName": "Apparel & Accessories > Clothing > Shirts & Tops > T-Shirts"},
        "variants": {
            "nodes": [
                {
                    "id": "gid://shopify/ProductVariant/1",
                    "title": "Black / M",
                    "sku": "TEE-BLK-M",
                    "taxable": True,
                    "availableForSale": True,
                    "inventoryItem": inventory,
                }
            ]
        },
    }


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (250, "GRAMS", 250.0),
        (0.25, "KILOGRAMS", 250.0),
        (1, "POUNDS", 453.59237),
        (1, "OUNCES", 28.349523125),
    ],
)
def test_weight_conversion(value: float, unit: str, expected: float) -> None:
    assert weight_to_grams(value, unit) == pytest.approx(expected)


def test_zero_weight_is_missing_not_invented() -> None:
    assert weight_to_grams(0, "GRAMS") is None


def test_unknown_weight_unit_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported weight unit"):
        weight_to_grams(1, "STONE")


def test_parser_preserves_shopify_compliance_values() -> None:
    record = parse_product_node(_product_node())[0]
    assert record.compliance.hs_code == "610910"
    assert record.compliance.country_of_origin == "CN"
    assert record.compliance.weight_grams == pytest.approx(250.0)
    assert record.requires_shipping is True
    assert record.taxable is True


def test_parser_does_not_infer_missing_hs_or_origin() -> None:
    product = _product_node(
        harmonizedSystemCode=None,
        countryCodeOfOrigin=None,
        measurement={"weight": None},
    )
    record = parse_product_node(product)[0]
    assert record.compliance.hs_code is None
    assert record.compliance.country_of_origin is None
    assert record.compliance.weight_grams is None


def test_vendor_and_product_type_are_observed_not_compliance_proof() -> None:
    product = _product_node(
        harmonizedSystemCode=None,
        countryCodeOfOrigin=None,
    )
    product["vendor"] = "Print On Demand Vendor"
    product["productType"] = "T-Shirt"
    record = parse_product_node(product)[0]
    assert record.vendor == "Print On Demand Vendor"
    assert record.product_type == "T-Shirt"
    assert record.compliance.hs_code is None
    assert record.compliance.country_of_origin is None


def test_parser_handles_comma_delimited_legacy_tags() -> None:
    product = _product_node()
    product["tags"] = "streetwear, pod"
    record = parse_product_node(product)[0]
    assert record.tags == ("streetwear", "pod")
