#!/usr/bin/env python3
"""
international_readiness_backfill.py

Operational Shopify international-readiness backfill for active and draft
products (archived products are excluded).

This is intentionally separate from Compliance V2's evidence-first customs
pipeline. Compliance V2 remains the audited source of truth for verified customs
facts. This script exists for store readiness: it fills missing Shopify inventory
item weight, HS code, and country of origin using the best available live product
signals and conservative fallback values so products are not blocked from
international checkout once published.

Rules:
- Never overwrites existing values unless --overwrite is passed.
- Defaults to dry-run. Pass --apply to write.
- Customs fallbacks require --allow-estimated-customs.
- Fallback COO is configurable with --fallback-coo or FALLBACK_COO.
- Writes Shopify InventoryItem fields via inventoryItemUpdate.
- Product statuses scanned are configurable with --statuses (default:
  active,draft).

Usage:
  python scripts/international_readiness_backfill.py
  python scripts/international_readiness_backfill.py --allow-estimated-customs
  python scripts/international_readiness_backfill.py --allow-estimated-customs --apply
  python scripts/international_readiness_backfill.py --statuses active
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.shopify import _graphql  # noqa: E402

FETCH_PRODUCTS_BY_STATUS = """
query($cursor: String, $statusQuery: String!) {
  products(first: 50, after: $cursor, query: $statusQuery) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      title
      status
      vendor
      productType
      descriptionHtml
      category { fullName name }
      tags
      variants(first: 100) {
        nodes {
          id
          title
          sku
          selectedOptions { name value }
          inventoryItem {
            id
            harmonizedSystemCode
            countryCodeOfOrigin
            requiresShipping
            measurement { weight { value unit } }
          }
        }
      }
    }
  }
}
"""

UPDATE_INVENTORY_ITEM = """
mutation inventoryItemUpdate($id: ID!, $input: InventoryItemInput!) {
  inventoryItemUpdate(id: $id, input: $input) {
    inventoryItem {
      id
      harmonizedSystemCode
      countryCodeOfOrigin
      measurement { weight { value unit } }
    }
    userErrors { field message }
  }
}
"""

_WEIGHT_UNIT_FACTORS = {
    "GRAMS": 1.0,
    "KILOGRAMS": 1000.0,
    "POUNDS": 453.59237,
    "OUNCES": 28.349523125,
}

# Flat weights for accessories that aren't sold/measured by fabric GSM.
ACCESSORY_WEIGHT_FALLBACKS_G = {
    "hat": 120.0,
    "cap": 120.0,
    "trucker": 120.0,
}

# National/industry-average fabric weight (grams per square meter) by garment
# category, used only when the listing itself doesn't state a GSM. This feeds
# the same gsm-to-garment-weight formula as an explicitly stated GSM (see
# infer_weight_grams) rather than standing in as a flat garment weight.
# Ordered before "shirt"/"tee": "sweatshirt" and "crewneck" contain the
# substring "shirt", so keyword_lookup's first-match iteration would
# otherwise misclassify them as a light t-shirt.
AVERAGE_GSM_BY_CATEGORY = {
    "hoodie": 320.0,
    "sweatshirt": 280.0,
    "crewneck": 280.0,
    "fleece": 300.0,
    "jacket": 300.0,
    "outerwear": 300.0,
    "sweatpants": 280.0,
    "pants": 280.0,
    "jean": 400.0,
    "jeans": 400.0,
    "shorts": 220.0,
    "polo": 200.0,
    "tank": 160.0,
    "t-shirt": 180.0,
    "t shirt": 180.0,
    "tee": 180.0,
    "shirt": 180.0,
}
DEFAULT_AVERAGE_GSM = 180.0  # generic lightweight-knit fallback (t-shirt-equivalent)

# Garment area/weight multipliers applied to GSM (stated or averaged) to
# estimate finished garment weight, grouped by cut.
_HEAVY_TOP_KEYWORDS = ("hoodie", "sweatshirt", "fleece", "crewneck")
_BOTTOM_KEYWORDS = ("pants", "jean", "shorts", "sweatpants")
_HEAVY_TOP_MULTIPLIER = 1.9
_BOTTOM_MULTIPLIER = 1.6
_TOP_MULTIPLIER = 1.15

HS_FALLBACKS = {
    "hat": "650500",
    "cap": "650500",
    "trucker": "650500",
    "polo": "610510",
    "sweatpants": "610342",
    "pants": "610342",
    "shorts": "610342",
    "jean": "620342",
    "jeans": "620342",
    "jacket": "610120",
    "outerwear": "610120",
    "hoodie": "611020",
    "sweatshirt": "611020",
    "crewneck": "611020",
    "fleece": "611020",
    "tank": "610910",
    "t-shirt": "610910",
    "t shirt": "610910",
    "tee": "610910",
    "shirt": "610910",
}

_GSM_RE = re.compile(r"(\d{3})\s*gsm", re.IGNORECASE)
_VALID_HS_RE = re.compile(r"^\d{6,10}$")


@dataclass(frozen=True, slots=True)
class PlannedVariantUpdate:
    product_title: str
    variant_title: str
    sku: str | None
    inventory_item_id: str
    old_weight_grams: float | None
    new_weight_grams: float | None
    old_hs_code: str | None
    new_hs_code: str | None
    old_coo: str | None
    new_coo: str | None
    reasons: tuple[str, ...]


def normalize_text(*parts: Any) -> str:
    return " ".join(str(part or "") for part in parts).lower()


def weight_to_grams(weight: dict | None) -> float | None:
    if not weight:
        return None
    value = weight.get("value")
    unit = str(weight.get("unit") or "").upper()
    if value is None or unit not in _WEIGHT_UNIT_FACTORS:
        return None
    grams = float(value) * _WEIGHT_UNIT_FACTORS[unit]
    return grams if grams > 0 else None


def keyword_lookup(text: str, mapping: dict[str, Any]) -> Any | None:
    for keyword, value in mapping.items():
        if keyword in text:
            return value
    return None


def infer_weight_grams(product: dict, variant: dict) -> tuple[float, str]:
    text = normalize_text(
        product.get("title"),
        product.get("productType"),
        (product.get("category") or {}).get("fullName"),
        " ".join(product.get("tags") or []),
        variant.get("title"),
        product.get("descriptionHtml"),
    )

    accessory_weight = keyword_lookup(text, ACCESSORY_WEIGHT_FALLBACKS_G)
    if accessory_weight is not None:
        return accessory_weight, "fixed_weight_accessory"

    gsm_match = _GSM_RE.search(text)
    if gsm_match:
        gsm = float(gsm_match.group(1))
        gsm_source = f"stated_{gsm_match.group(1)}gsm"
    else:
        gsm = keyword_lookup(text, AVERAGE_GSM_BY_CATEGORY) or DEFAULT_AVERAGE_GSM
        gsm_source = f"average_{int(gsm)}gsm_for_category"

    if any(keyword in text for keyword in _HEAVY_TOP_KEYWORDS):
        # Heavy streetwear tops often move from ~650g into 900g+ territory.
        return round(gsm * _HEAVY_TOP_MULTIPLIER, 0), f"estimated_weight_from_{gsm_source}_heavy_top"
    if any(keyword in text for keyword in _BOTTOM_KEYWORDS):
        return round(gsm * _BOTTOM_MULTIPLIER, 0), f"estimated_weight_from_{gsm_source}_bottom"
    return round(gsm * _TOP_MULTIPLIER, 0), f"estimated_weight_from_{gsm_source}_top"


def infer_hs_code(product: dict, variant: dict) -> tuple[str, str]:
    text = normalize_text(
        product.get("title"),
        product.get("productType"),
        (product.get("category") or {}).get("fullName"),
        " ".join(product.get("tags") or []),
        variant.get("title"),
    )
    hs = keyword_lookup(text, HS_FALLBACKS) or "610910"
    return hs, "estimated_hs_from_product_type"


def normalize_hs(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[\s.]", "", value)
    return normalized if _VALID_HS_RE.match(normalized) else None


def fetch_products_by_status(statuses: list[str]) -> list[dict]:
    status_query = " OR ".join(f"status:{status}" for status in statuses)
    products: list[dict] = []
    cursor = None
    while True:
        data = _graphql(FETCH_PRODUCTS_BY_STATUS, {"cursor": cursor, "statusQuery": status_query})
        page = data["data"]["products"]
        products.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return products


def build_plan(
    products: list[dict],
    *,
    fallback_coo: str,
    allow_estimated_customs: bool,
    overwrite: bool,
) -> list[PlannedVariantUpdate]:
    plans: list[PlannedVariantUpdate] = []
    fallback_coo = fallback_coo.strip().upper()
    if allow_estimated_customs and not re.fullmatch(r"[A-Z]{2}", fallback_coo):
        raise ValueError("fallback COO must be a 2-letter country code, e.g. CN or US")

    for product in products:
        variants = ((product.get("variants") or {}).get("nodes") or [])
        for variant in variants:
            inventory = variant.get("inventoryItem") or {}
            if not inventory.get("requiresShipping", True):
                continue

            current_weight = weight_to_grams(((inventory.get("measurement") or {}).get("weight") or None))
            current_hs = normalize_hs(inventory.get("harmonizedSystemCode"))
            current_coo = (inventory.get("countryCodeOfOrigin") or "").strip().upper() or None

            reasons: list[str] = []
            new_weight = current_weight
            new_hs = current_hs
            new_coo = current_coo

            if overwrite or current_weight is None:
                new_weight, reason = infer_weight_grams(product, variant)
                reasons.append(reason)

            if allow_estimated_customs and (overwrite or current_hs is None):
                new_hs, reason = infer_hs_code(product, variant)
                reasons.append(reason)

            if allow_estimated_customs and (overwrite or current_coo is None):
                new_coo = fallback_coo
                reasons.append(f"estimated_coo_from_config:{fallback_coo}")

            changed = (
                new_weight != current_weight
                or new_hs != current_hs
                or new_coo != current_coo
            )
            if changed:
                plans.append(
                    PlannedVariantUpdate(
                        product_title=str(product.get("title") or ""),
                        variant_title=str(variant.get("title") or ""),
                        sku=variant.get("sku") or None,
                        inventory_item_id=str(inventory.get("id") or ""),
                        old_weight_grams=current_weight,
                        new_weight_grams=new_weight,
                        old_hs_code=current_hs,
                        new_hs_code=new_hs,
                        old_coo=current_coo,
                        new_coo=new_coo,
                        reasons=tuple(reasons),
                    )
                )
    return plans


def apply_plan(plan: PlannedVariantUpdate) -> None:
    payload: dict[str, Any] = {}
    if plan.new_hs_code:
        payload["harmonizedSystemCode"] = plan.new_hs_code
    if plan.new_coo:
        payload["countryCodeOfOrigin"] = plan.new_coo
    if plan.new_weight_grams is not None and plan.new_weight_grams > 0:
        payload["measurement"] = {"weight": {"value": plan.new_weight_grams, "unit": "GRAMS"}}

    result = _graphql(UPDATE_INVENTORY_ITEM, {"id": plan.inventory_item_id, "input": payload})
    errors = result.get("data", {}).get("inventoryItemUpdate", {}).get("userErrors", [])
    if errors:
        raise RuntimeError(f"Shopify userErrors for {plan.inventory_item_id}: {errors}")


def plans_to_csv(plans: list[PlannedVariantUpdate]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "product_title",
        "variant_title",
        "sku",
        "inventory_item_id",
        "old_weight_grams",
        "new_weight_grams",
        "old_hs_code",
        "new_hs_code",
        "old_coo",
        "new_coo",
        "reasons",
    ])
    for plan in plans:
        writer.writerow([
            plan.product_title,
            plan.variant_title,
            plan.sku or "",
            plan.inventory_item_id,
            plan.old_weight_grams or "",
            plan.new_weight_grams or "",
            plan.old_hs_code or "",
            plan.new_hs_code or "",
            plan.old_coo or "",
            plan.new_coo or "",
            ";".join(plan.reasons),
        ])
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Shopify international readiness fields")
    parser.add_argument("--apply", action="store_true", help="Write changes to Shopify. Default is dry-run.")
    parser.add_argument(
        "--allow-estimated-customs",
        action="store_true",
        help="Allow estimated HS/COO fallback writes. Without this, only missing weights are planned.",
    )
    parser.add_argument("--fallback-coo", default=os.getenv("FALLBACK_COO", "CN"), help="2-letter COO fallback for missing COO. Default: CN")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing values. Default only fills missing values.")
    parser.add_argument("--csv-out", default="international_readiness_backfill_report.csv")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between writes to avoid rate pressure")
    parser.add_argument(
        "--statuses",
        default="active,draft",
        help="Comma-separated Shopify product statuses to scan (e.g. active,draft). Default: active,draft",
    )
    args = parser.parse_args()

    statuses = [s.strip() for s in args.statuses.split(",") if s.strip()]
    products = fetch_products_by_status(statuses)
    plans = build_plan(
        products,
        fallback_coo=args.fallback_coo,
        allow_estimated_customs=args.allow_estimated_customs,
        overwrite=args.overwrite,
    )

    with open(args.csv_out, "w") as f:
        f.write(plans_to_csv(plans))

    print("International readiness backfill")
    print(f"  Product statuses scanned: {', '.join(statuses)}")
    print(f"  Products fetched: {len(products)}")
    print(f"  Planned variant updates: {len(plans)}")
    print(f"  Estimated customs enabled: {args.allow_estimated_customs}")
    print(f"  Fallback COO: {args.fallback_coo.strip().upper()}")
    print(f"  Overwrite existing values: {args.overwrite}")
    print(f"  Report: {args.csv_out}")

    if not args.apply:
        print("  Dry run only. Pass --apply to write changes.")
        return

    errors = 0
    for idx, plan in enumerate(plans, start=1):
        try:
            apply_plan(plan)
            print(f"  [{idx}/{len(plans)}] applied {plan.product_title[:60]} / {plan.variant_title}")
        except Exception as exc:  # noqa: BLE001 - CLI must continue and report all failures
            errors += 1
            print(f"  [{idx}/{len(plans)}] ERROR {plan.inventory_item_id}: {exc}", file=sys.stderr)
        time.sleep(args.sleep)

    print(f"Complete. applied={len(plans) - errors} errors={errors}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
