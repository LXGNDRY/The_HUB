"""
api/routers/gmc.py — Google Merchant Center API endpoints

Inspection endpoints (GET):
  GET  /api/gmc/disapprovals          — Live GMC disapprovals + critical item issues
  GET  /api/gmc/product-statuses      — All GMC product statuses (up to 250)
  GET  /api/gmc/shipping-drift        — Compare Shopify vs GMC shipping countries
  GET  /api/gmc/title-rotation/state  — Load title rotation state from GCS

Autonomous action endpoints (POST):
  POST /api/gmc/fix-disapprovals      — Patch brand + identifierExists on disapproved products
  POST /api/gmc/apply-attribute-rules — Apply standard apparel attribute rules to all feeds
  POST /api/gmc/sync-shipping         — Push missing Shopify countries into GMC shipping settings
  POST /api/gmc/title-rotation/run    — Trigger GMC title rotation job immediately
  POST /api/gmc/run-all               — fix-disapprovals → apply-attribute-rules → sync-shipping
"""

import os
import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("gcp-bot.api.gmc")
router = APIRouter()

MERCHANT_ID = os.getenv("GMC_MERCHANT_ID", "")

# Transit time defaults for new GMC shipping services
_DOMESTIC_TRANSIT = (3, 4)
_INTL_TRANSIT = (6, 12)
_DOMESTIC_ZONE_NAMES = {"domestic", "united states", "us"}

# Currency fallback map (country → ISO currency) used when not in Shopify's response
_CURRENCY_MAP = {
    "US": "USD", "GB": "GBP", "CA": "CAD", "AU": "AUD", "NZ": "NZD",
    "JP": "JPY", "KR": "KRW", "SG": "SGD", "HK": "HKD", "CH": "CHF",
    "NO": "NOK", "SE": "SEK", "DK": "DKK", "CZ": "CZK", "PL": "PLN",
    "HU": "HUF", "RO": "RON", "IL": "ILS", "MX": "MXN", "AR": "ARS",
    "CL": "CLP", "CO": "COP", "EC": "USD", "PE": "PEN", "DO": "DOP",
    "SV": "USD", "GT": "GTQ", "JM": "JMD", "PA": "USD", "PR": "USD",
    "TT": "TTD", "KZ": "KZT", "AM": "AMD", "GE": "GEL", "MA": "MAD",
    "EG": "EGP", "JO": "JOD", "LB": "LBP", "ZA": "ZAR", "MY": "MYR",
    "AE": "AED", "QA": "QAR", "KW": "KWD", "BH": "BHD", "SA": "SAR",
    "FR": "EUR", "DE": "EUR", "IE": "EUR", "ES": "EUR", "IT": "EUR",
    "NL": "EUR", "BE": "EUR", "PT": "EUR", "GR": "EUR", "AT": "EUR",
    "FI": "EUR", "SK": "EUR",
}


# ============================================================
# Internal helpers
# ============================================================

def _require_merchant_id():
    if not MERCHANT_ID:
        raise HTTPException(status_code=503, detail="GMC_MERCHANT_ID not configured")
    return MERCHANT_ID


def _build_content_service():
    from googleapiclient.discovery import build
    from auth.credentials import get_credentials
    return build("content", "v2.1", credentials=get_credentials(), cache_discovery=False)


def _shopify_get(path: str) -> dict:
    from modules.shopify import _get
    return _get(path)


def _build_gmc_shipping_service(country_code, is_free, price, currency, zone_name):
    is_domestic = zone_name.lower() in _DOMESTIC_ZONE_NAMES
    transit_min, transit_max = _DOMESTIC_TRANSIT if is_domestic else _INTL_TRANSIT
    price_str = "0" if is_free else str(price)
    return {
        "name": f"{'free' if is_free else 'express'}_{country_code}_sync",
        "active": True,
        "deliveryCountry": country_code,
        "currency": currency,
        "deliveryTime": {
            "minTransitTimeInDays": transit_min,
            "maxTransitTimeInDays": transit_max,
            "minHandlingTimeInDays": 2,
            "maxHandlingTimeInDays": 2,
        },
        "shipmentType": "delivery",
        "rateGroups": [{"singleValue": {"flatRate": {"value": price_str, "currency": currency}}}],
    }


# ============================================================
# Shared action logic (also imported by scheduler jobs)
# ============================================================

def _do_fix_disapprovals(merchant_id: str, service) -> dict:
    """
    Patch brand="Legendary Branding" and identifierExists=False on all
    disapproved GMC products. Returns {patched, skipped, errors}.
    """
    statuses = service.productstatuses().list(
        merchantId=merchant_id, maxResults=250
    ).execute()

    disapproved_ids = []
    for item in statuses.get("resources", []):
        for ds in item.get("destinationStatuses", []):
            if ds.get("status") == "disapproved":
                disapproved_ids.append(item.get("productId", ""))
                break

    if not disapproved_ids:
        return {"patched": 0, "skipped": 0, "errors": []}

    patched = 0
    skipped = 0
    errors = []

    # Process in batches of 100
    for batch_start in range(0, len(disapproved_ids), 100):
        batch = disapproved_ids[batch_start:batch_start + 100]
        entries = []
        for i, product_id in enumerate(batch):
            entries.append({
                "batchId": i + 1,
                "merchantId": merchant_id,
                "method": "update",
                "productId": product_id,
                "product": {
                    "brand": "Legendary Branding",
                    "identifierExists": False,
                },
                "updateMask": "brand,identifierExists",
            })

        try:
            result = service.products().custombatch(body={"entries": entries}).execute()
            for entry in result.get("entries", []):
                if entry.get("errors"):
                    errors.append({
                        "product_id": batch[entry["batchId"] - 1],
                        "error": entry["errors"].get("message", "unknown"),
                    })
                else:
                    patched += 1
        except Exception as e:
            errors.append({"batch_start": batch_start, "error": str(e)})

    skipped = len(disapproved_ids) - patched - len(errors)
    return {"patched": patched, "skipped": skipped, "errors": errors}


def _do_apply_attribute_rules(merchant_id: str, service) -> dict:
    """
    Apply standard apparel attribute rules (age_group=adult, gender=unisex,
    identifierExists=false) to all GMC datafeeds that have products.
    Returns {updated_feeds, skipped_feeds, errors}.
    """
    STANDARD_RULES = [
        {"attributeName": "ageGroup", "attributeValue": "adult"},
        {"attributeName": "gender", "attributeValue": "unisex"},
        {"attributeName": "identifierExists", "attributeValue": "false"},
    ]

    feeds_resp = service.datafeeds().list(merchantId=merchant_id).execute()
    feeds = feeds_resp.get("resources", [])

    updated = 0
    skipped = 0
    errors = []

    for feed in feeds:
        feed_id = feed.get("id")
        try:
            # Check product count — skip empty feeds
            status = service.datafeedstatuses().get(
                merchantId=merchant_id, datafeedId=feed_id
            ).execute()
            if status.get("itemsTotal", 0) == 0:
                skipped += 1
                continue

            existing_rules = feed.get("attributeRules", [])
            existing_attrs = {r.get("attributeName") for r in existing_rules}
            missing_rules = [r for r in STANDARD_RULES if r["attributeName"] not in existing_attrs]

            if not missing_rules:
                skipped += 1
                continue

            feed["attributeRules"] = existing_rules + missing_rules
            service.datafeeds().update(
                merchantId=merchant_id, datafeedId=feed_id, body=feed
            ).execute()
            updated += 1

        except Exception as e:
            errors.append({"feed_id": feed_id, "error": str(e)})

    return {"updated_feeds": updated, "skipped_feeds": skipped, "errors": errors}


def _do_sync_shipping(merchant_id: str, service) -> dict:
    """
    Fetch Shopify shipping zones, diff against GMC shipping services,
    and push any missing countries into GMC. Returns {added, conflicts_fixed,
    matched, still_missing}.
    """
    # Fetch Shopify zones directly (same approach as sync_gmc_shipping.py)
    zones_data = _shopify_get("/shipping_zones.json")
    shopify_rates = {}  # country_code → {free, express_price, zone_name, currency}

    for zone in zones_data.get("shipping_zones", []):
        zone_name = zone.get("name", "")
        price_rates = zone.get("price_based_shipping_rates", [])
        weight_rates = zone.get("weight_based_shipping_rates", [])
        all_rates = price_rates + weight_rates

        has_free = any(float(r.get("price", "999") or "999") == 0 for r in all_rates)
        express = next((r for r in all_rates if float(r.get("price", "0") or "0") > 0), None)
        express_price = str(float(express["price"])) if express else None

        for country in zone.get("countries", []):
            code = country.get("code", "")
            if code:
                shopify_rates[code] = {
                    "free": has_free,
                    "express_price": express_price,
                    "zone_name": zone_name,
                    "currency": country.get("currency") or _CURRENCY_MAP.get(code, "USD"),
                }

    # Fetch GMC settings
    gmc_settings = service.shippingsettings().get(
        merchantId=merchant_id, accountId=merchant_id
    ).execute()

    # Build GMC country→service_types map
    gmc_coverage = {}
    for svc in gmc_settings.get("services", []):
        code = svc.get("deliveryCountry", "")
        rate_val = (
            svc.get("rateGroups", [{}])[0]
            .get("singleValue", {})
            .get("flatRate", {})
            .get("value", "?")
        )
        svc_type = "free" if rate_val == "0" else f"paid_{rate_val}"
        gmc_coverage.setdefault(code, []).append(svc_type)

    to_add = []
    conflicts = []
    matched = []

    for code, shopify in shopify_rates.items():
        gmc_svcs = gmc_coverage.get(code, [])
        if not gmc_svcs:
            to_add.append((code, shopify))
        else:
            gmc_has_free = any(s == "free" for s in gmc_svcs)
            if shopify["free"] and not gmc_has_free:
                conflicts.append((code, shopify))
            else:
                matched.append(code)

    if not to_add and not conflicts:
        return {
            "added": [],
            "conflicts_fixed": [],
            "matched": len(matched),
            "still_missing": [],
            "in_sync": True,
        }

    new_services = list(gmc_settings.get("services", []))

    for code, shopify in to_add:
        currency = shopify["currency"]
        zone_name = shopify["zone_name"]
        if shopify["free"]:
            new_services.append(_build_gmc_shipping_service(code, True, "0", currency, zone_name))
        if shopify["express_price"]:
            new_services.append(_build_gmc_shipping_service(
                code, False, shopify["express_price"], currency, zone_name
            ))

    for code, shopify in conflicts:
        currency = shopify["currency"]
        zone_name = shopify["zone_name"]
        new_services.append(_build_gmc_shipping_service(code, True, "0", currency, zone_name))

    gmc_settings["services"] = new_services
    service.shippingsettings().update(
        merchantId=merchant_id, accountId=merchant_id, body=gmc_settings
    ).execute()

    # Verify
    updated = service.shippingsettings().get(
        merchantId=merchant_id, accountId=merchant_id
    ).execute()
    updated_coverage = {svc.get("deliveryCountry", "") for svc in updated.get("services", [])}
    still_missing = [c for c in shopify_rates if c not in updated_coverage]

    return {
        "added": [c for c, _ in to_add],
        "conflicts_fixed": [c for c, _ in conflicts],
        "matched": len(matched),
        "still_missing": still_missing,
        "in_sync": len(still_missing) == 0,
    }


# ============================================================
# GET — Inspection endpoints
# ============================================================

@router.get("/disapprovals")
def get_disapprovals():
    """Fetch current GMC disapprovals and critical item-level issues."""
    merchant_id = _require_merchant_id()
    try:
        service = _build_content_service()
        statuses = service.productstatuses().list(
            merchantId=merchant_id, maxResults=250
        ).execute()

        disapproved = []
        flagged = []

        for item in statuses.get("resources", []):
            product_id = item.get("productId", "")
            title = item.get("title", product_id)

            for ds in item.get("destinationStatuses", []):
                if ds.get("status") == "disapproved":
                    disapproved.append({"product_id": product_id, "title": title})
                    break

            for issue in item.get("itemLevelIssues", []):
                if issue.get("severity") == "error":
                    flagged.append({
                        "product_id": product_id,
                        "title": title,
                        "issue": issue.get("description", ""),
                        "code": issue.get("code", ""),
                    })
                    break

        return {
            "merchant_id": merchant_id,
            "disapproved_count": len(disapproved),
            "flagged_count": len(flagged),
            "disapproved": disapproved,
            "flagged": flagged,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] get_disapprovals failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/product-statuses")
def get_product_statuses(max_results: int = 50):
    """List GMC product statuses. max_results capped at 250."""
    merchant_id = _require_merchant_id()
    max_results = min(max_results, 250)
    try:
        service = _build_content_service()
        resp = service.productstatuses().list(
            merchantId=merchant_id, maxResults=max_results
        ).execute()

        products = []
        for item in resp.get("resources", []):
            dest_statuses = {
                ds.get("destination", ""): ds.get("status", "")
                for ds in item.get("destinationStatuses", [])
            }
            products.append({
                "product_id": item.get("productId", ""),
                "title": item.get("title", ""),
                "destination_statuses": dest_statuses,
                "item_issues_count": len(item.get("itemLevelIssues", [])),
            })

        return {
            "merchant_id": merchant_id,
            "count": len(products),
            "next_page_token": resp.get("nextPageToken"),
            "products": products,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] get_product_statuses failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shipping-drift")
def get_shipping_drift():
    """
    Compare active Shopify shipping zones against GMC shipping services.
    Returns countries present in one but missing from the other.
    """
    merchant_id = _require_merchant_id()
    try:
        service = _build_content_service()

        # Parse Shopify zones directly — shipping_rates_summary() returns a flat
        # rates list, not zones with countries, so we call the raw endpoint instead.
        zones_data = _shopify_get("/shipping_zones.json")
        shopify_countries = set()
        for zone in zones_data.get("shipping_zones", []):
            for country in zone.get("countries", []):
                code = country.get("code", "")
                if code:
                    shopify_countries.add(code.upper())

        gmc_resp = service.shippingsettings().get(
            merchantId=merchant_id, accountId=merchant_id
        ).execute()
        gmc_countries = set()
        for svc in gmc_resp.get("services", []):
            code = svc.get("deliveryCountry", "")
            if code:
                gmc_countries.add(code.upper())

        missing_from_gmc = sorted(shopify_countries - gmc_countries)
        missing_from_shopify = sorted(gmc_countries - shopify_countries)

        return {
            "merchant_id": merchant_id,
            "in_sync": not missing_from_gmc and not missing_from_shopify,
            "shopify_country_count": len(shopify_countries),
            "gmc_country_count": len(gmc_countries),
            "missing_from_gmc": missing_from_gmc,
            "missing_from_shopify": missing_from_shopify,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] get_shipping_drift failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/title-rotation/state")
def get_title_rotation_state():
    """Load the current GMC title rotation state from GCS (lb-feed-state bucket)."""
    sa_key_json = os.getenv("GCP_SA_KEY_JSON", "")
    if not sa_key_json:
        raise HTTPException(status_code=503, detail="GCP_SA_KEY_JSON not configured")
    _require_merchant_id()

    try:
        import sys
        scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from title_rotation_module import load_state

        state = load_state(sa_key_json)
        return {
            "last_run": state.get("last_run"),
            "products_tracked": len(state.get("products", {})),
            "state": state,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] get_title_rotation_state failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# POST — Autonomous action endpoints
# ============================================================

@router.post("/fix-disapprovals")
def fix_disapprovals():
    """
    Automatically patch brand="Legendary Branding" and identifierExists=False
    on all currently disapproved GMC products via custombatch.
    """
    merchant_id = _require_merchant_id()
    try:
        service = _build_content_service()
        result = _do_fix_disapprovals(merchant_id, service)
        logger.info("[gmc] fix_disapprovals: %s", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] fix_disapprovals failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply-attribute-rules")
def apply_attribute_rules():
    """
    Apply standard apparel attribute rules (age_group=adult, gender=unisex,
    identifierExists=false) to all GMC datafeeds that have products.
    """
    merchant_id = _require_merchant_id()
    try:
        service = _build_content_service()
        result = _do_apply_attribute_rules(merchant_id, service)
        logger.info("[gmc] apply_attribute_rules: %s", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] apply_attribute_rules failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-shipping")
def sync_shipping():
    """
    Diff Shopify shipping zones against GMC shipping services and push
    any missing or mismatched countries into GMC automatically.
    """
    merchant_id = _require_merchant_id()
    try:
        service = _build_content_service()
        result = _do_sync_shipping(merchant_id, service)
        logger.info("[gmc] sync_shipping: %s", result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[gmc] sync_shipping failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/title-rotation/run")
def run_title_rotation():
    """
    Trigger the GMC title rotation job immediately (synchronous).
    Advances rotation decisions and saves updated state to GCS.
    """
    _require_merchant_id()
    if not os.getenv("GCP_SA_KEY_JSON", ""):
        raise HTTPException(status_code=503, detail="GCP_SA_KEY_JSON not configured")

    try:
        from scheduler.jobs import gmc_title_rotation_job
        gmc_title_rotation_job()
        return {"status": "completed", "job": "gmc_title_rotation"}
    except Exception as e:
        logger.error("[gmc] run_title_rotation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-all")
def run_all():
    """
    Run all three GMC autonomous fix actions in sequence:
      1. fix-disapprovals   — patch brand + identifierExists on disapproved products
      2. apply-attribute-rules — apply age_group/gender/identifierExists to all feeds
      3. sync-shipping      — push missing Shopify countries into GMC shipping

    Returns per-step results. Steps run independently; one failure does not
    stop subsequent steps.
    """
    merchant_id = _require_merchant_id()
    service = _build_content_service()
    results = {}

    for step_name, step_fn in [
        ("fix_disapprovals", _do_fix_disapprovals),
        ("apply_attribute_rules", _do_apply_attribute_rules),
        ("sync_shipping", _do_sync_shipping),
    ]:
        try:
            results[step_name] = step_fn(merchant_id, service)
            logger.info("[gmc] run_all/%s: %s", step_name, results[step_name])
        except Exception as e:
            logger.error("[gmc] run_all/%s failed: %s", step_name, e)
            results[step_name] = {"error": str(e)}

    return results
