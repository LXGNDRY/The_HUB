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
    # 260 stated GSM x top multiplier (1.15) = 299g; no artificial floor.
    assert infer_weight_grams(product, variant)[0] == 299.0


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


def test_hoodie_without_stated_gsm_uses_category_average_not_light_flat_weight():
    """A hoodie/sweatshirt with no GSM in its listing must not fall back to a
    light t-shirt weight just because "sweatshirt" contains "shirt"."""
    product = _product(
        "Marque Legendaire Oversized Crewneck Sweatshirt",
        product_type="Apparel & Accessories > Clothing > Activewear > Sweatshirts & Hoodies",
    )
    variant = _variant(product)

    weight, reason = infer_weight_grams(product, variant)
    assert weight >= 500
    assert "average" in reason


def test_crewneck_tshirt_is_not_misclassified_as_heavy_sweatshirt():
    """"Crewneck" is a neckline shared with t-shirts, not exclusively a
    sweatshirt cue — an explicit t-shirt must win over it."""
    product = _product("Classic Crewneck Cotton T-Shirt | 180 GSM")
    variant = _variant(product)

    assert infer_hs_code(product, variant)[0] == "610910"
    weight, reason = infer_weight_grams(product, variant)
    assert weight < 500
    assert "heavy_top" not in reason


def test_jean_under_pants_taxonomy_is_classified_as_woven_denim_not_knit_pants():
    """Real catalog case: productType/category is ".../Pants" (contains the
    substring "pants"), but the title says "Jean" — jeans are woven (Ch. 62),
    not knit pants (Ch. 61), and must not be misclassified by the "pants"
    substring winning first."""
    product = _product(
        "GOAT Dept. Heavyweight Multi-Pocket Jean",
        product_type="Apparel & Accessories > Clothing > Pants",
        tags=["Baggy Jeans", "Denim"],
    )
    variant = _variant(product)

    assert infer_hs_code(product, variant)[0] == "620342"
    weight, reason = infer_weight_grams(product, variant)
    assert weight == 640.0  # 400 avg gsm (jean) x 1.6 bottom multiplier
    assert "bottom" in reason


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
