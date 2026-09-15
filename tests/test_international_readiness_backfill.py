from scripts.international_readiness_backfill import (
    build_plan,
    infer_hs_code,
    infer_weight_grams,
)


def _product(title, product_type="Apparel & Accessories > Clothing > Shirts & Tops", tags=None):
    return {
        "id": "gid://shopify/Product/1",
        "title": title,
        "status": "ACTIVE",
        "vendor": "Legendary Branding",
        "productType": product_type,
        "category": {"fullName": product_type},
        "tags": tags or [],
        "variants": {
            "nodes": [
                {
                    "id": "gid://shopify/ProductVariant/1",
                    "title": "Black / M",
                    "sku": "SKU-1",
                    "inventoryItem": {
                        "id": "gid://shopify/InventoryItem/1",
                        "requiresShipping": True,
                        "harmonizedSystemCode": None,
                        "countryCodeOfOrigin": None,
                        "measurement": {"weight": None},
                    },
                }
            ]
        },
    }


def _variant(product):
    return product["variants"]["nodes"][0]


def test_tshirt_hs_and_weight_fallback():
    product = _product("Savage Butterfly Essential Cotton T-Shirt | 260 GSM", tags=["Pure Cotton"])
    variant = _variant(product)

    assert infer_hs_code(product, variant)[0] == "610910"
    assert infer_weight_grams(product, variant)[0] >= 300


def test_polo_hs_fallback():
    product = _product("Marque Legendaire Raglan Polo Shirt | 220 GSM")
    assert infer_hs_code(product, _variant(product))[0] == "610510"


def test_hoodie_hs_and_heavy_weight_fallback():
    product = _product(
        "Marque Legendaire Cropped Oversized Zip-Up Hoodie | 460GSM",
        product_type="Apparel & Accessories > Clothing > Activewear > Hoodies",
    )
    variant = _variant(product)

    assert infer_hs_code(product, variant)[0] == "611020"
    assert infer_weight_grams(product, variant)[0] >= 874


def test_existing_values_are_not_overwritten_by_default():
    product = _product("Complete Tee")
    inv = product["variants"]["nodes"][0]["inventoryItem"]
    inv["harmonizedSystemCode"] = "610910"
    inv["countryCodeOfOrigin"] = "CN"
    inv["measurement"] = {"weight": {"value": 300, "unit": "GRAMS"}}

    plans = build_plan([product], fallback_coo="CN", allow_estimated_customs=True, overwrite=False)

    assert plans == []


def test_missing_customs_requires_explicit_flag():
    product = _product("Missing Tee")

    plans = build_plan([product], fallback_coo="CN", allow_estimated_customs=False, overwrite=False)

    assert len(plans) == 1
    assert plans[0].new_hs_code is None
    assert plans[0].new_coo is None
    assert plans[0].new_weight_grams is not None


def test_missing_customs_can_be_planned_with_flag():
    product = _product("Missing Tee")

    plans = build_plan([product], fallback_coo="CN", allow_estimated_customs=True, overwrite=False)

    assert len(plans) == 1
    assert plans[0].new_hs_code == "610910"
    assert plans[0].new_coo == "CN"
    assert plans[0].new_weight_grams is not None
