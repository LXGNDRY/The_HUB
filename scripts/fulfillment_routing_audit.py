"""Pure, read-only fulfillment routing checks.

Consumes an explicitly exported JSON snapshot; never calls Shopify or mutates store data.
Expected input: {"locations": [{"id": "...", "name": "...", "shipsInventory": true,
"fulfillsOnlineOrders": true}], "variants": [{"id": "...", "sellable": true,
"inventory_locations": ["location-id"], "shipping_locations": ["location-id"]}]}.
Unknown/omitted data is reported as incomplete, not silently accepted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def audit(snapshot: dict, brand_location_name: str = "LEGENDARY BRANDING") -> dict:
    issues = []
    locations = snapshot.get("locations")
    variants = snapshot.get("variants")
    if not isinstance(locations, list) or not isinstance(variants, list):
        return {"status": "incomplete", "issues": [{"code": "MISSING_DATA", "detail": "locations and variants arrays are required"}], "counts": {}}
    by_id = {}
    for location in locations:
        if not isinstance(location, dict) or not location.get("id"):
            issues.append({"code": "INVALID_LOCATION"})
            continue
        if location["id"] in by_id:
            issues.append({"code": "DUPLICATE_LOCATION", "location_id": location["id"]})
        by_id[location["id"]] = location
        if location.get("name", "").strip().casefold() == brand_location_name.casefold():
            if location.get("shipsInventory") is True or location.get("fulfillsOnlineOrders") is True:
                issues.append({"code": "BRAND_LOCATION_SHIPPING_ENABLED", "location_id": location["id"]})
    seen = set()
    sellable = 0
    for variant in variants:
        if not isinstance(variant, dict) or not variant.get("id"):
            issues.append({"code": "INVALID_VARIANT"})
            continue
        vid = variant["id"]
        if vid in seen:
            issues.append({"code": "DUPLICATE_VARIANT", "variant_id": vid})
        seen.add(vid)
        if variant.get("sellable") is not True:
            if "sellable" not in variant:
                issues.append({"code": "UNKNOWN_SELLABILITY", "variant_id": vid})
            continue
        sellable += 1
        inventory = variant.get("inventory_locations")
        shipping = variant.get("shipping_locations")
        if not isinstance(inventory, list) or not isinstance(shipping, list):
            issues.append({"code": "INCOMPLETE_VARIANT_ROUTING", "variant_id": vid})
            continue
        eligible = set(inventory) & set(shipping)
        eligible = {lid for lid in eligible if lid in by_id and by_id[lid].get("shipsInventory") is True and by_id[lid].get("fulfillsOnlineOrders") is True}
        if not eligible:
            issues.append({"code": "NO_ELIGIBLE_ORIGIN", "variant_id": vid})
    incomplete = any(i["code"] in {"INVALID_LOCATION", "INVALID_VARIANT", "UNKNOWN_SELLABILITY", "INCOMPLETE_VARIANT_ROUTING", "MISSING_DATA"} for i in issues)
    return {"status": "incomplete" if incomplete else ("exceptions" if issues else "pass"), "counts": {"locations": len(locations), "variants": len(variants), "sellable_variants": sellable}, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a read-only Shopify fulfillment snapshot")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, help="Write findings as JSON; no Shopify writes")
    args = parser.parse_args()
    result = audit(json.loads(args.snapshot.read_text(encoding="utf-8")))
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
