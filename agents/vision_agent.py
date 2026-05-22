"""
agents/vision_agent.py — NVIDIA NIM Vision Agent

Orchestrates vision-powered product enrichment for the Legendary Branding store.

Workflows:
  1. run_alt_text_audit(dry_run)   — Find all Shopify products missing alt text,
                                     generate via NIM, write back to Shopify.
  2. run_quality_audit()           — Check all product images for photo quality issues,
                                     return report without writing anything.
  3. run_description_gen(ids)      — Generate product descriptions for given product IDs.

Safe by default:
  - dry_run=True by default — previews all changes without writing to Shopify.
  - Skips products that already have alt text unless VISION_FORCE_OVERWRITE=true.
  - Logs every action — nothing silent.
"""

import os
import logging
from typing import Optional

from modules.nvidia_vision import NvidiaVisionModule
import modules.shopify as shopify

logger = logging.getLogger("gcp-bot.vision_agent")

DRY_RUN         = os.getenv("VISION_DRY_RUN", "true").lower() == "true"
FORCE_OVERWRITE = os.getenv("VISION_FORCE_OVERWRITE", "false").lower() == "true"


def run_alt_text_audit(dry_run: bool = DRY_RUN) -> dict:
    """
    Full pipeline:
      1. Pull all products + images from Shopify
      2. Collect images missing alt text
      3. Send each image URL to NIM Vision → get alt text
      4. PATCH alt text back to Shopify (unless dry_run=True)

    Returns summary dict: {total_images, missing_alt, updated, skipped, errors, dry_run, results}
    """
    vision = NvidiaVisionModule()
    logger.info("[vision_agent] Starting alt text audit. dry_run=%s", dry_run)

    # ── 1. Fetch all products (full detail for images) ─────────────────────────
    raw = shopify._get("/products.json", {"limit": 250, "fields": "id,title,images"})
    products = raw.get("products", [])

    if not products:
        return {"error": "No products returned from Shopify"}

    # ── 2. Collect images missing alt text ────────────────────────────────────
    missing = []
    total_images = 0

    for product in products:
        pid    = product["id"]
        title  = product.get("title", "")
        images = product.get("images", [])
        for img in images:
            total_images += 1
            current_alt = img.get("alt") or ""
            if not current_alt or FORCE_OVERWRITE:
                missing.append({
                    "product_id":    pid,
                    "product_title": title,
                    "image_id":      img["id"],
                    "image_url":     img["src"],
                    "current_alt":   current_alt,
                })

    logger.info(
        "[vision_agent] %d total images, %d missing alt text", total_images, len(missing)
    )

    if not missing:
        return {
            "total_images": total_images,
            "missing_alt":  0,
            "updated":      0,
            "skipped":      0,
            "errors":       0,
            "dry_run":      dry_run,
            "results":      [],
            "message":      "All product images already have alt text.",
        }

    # ── 3. Generate alt text via NIM ──────────────────────────────────────────
    image_urls  = [m["image_url"] for m in missing]
    nim_results = vision.batch_alt_text(image_urls)

    # ── 4. Write back to Shopify ──────────────────────────────────────────────
    updated = 0
    skipped = 0
    errors  = 0
    results = []

    for item, nim in zip(missing, nim_results):
        alt_text = nim.get("alt_text")
        error    = nim.get("error")

        if error or not alt_text:
            logger.error(
                "[vision_agent] NIM error for '%s' image %s: %s",
                item["product_title"], item["image_id"], error
            )
            errors += 1
            results.append({**item, "generated_alt": None, "status": "error", "error": error})
            continue

        logger.info(
            "[vision_agent] [%s] '%s' → '%s'",
            "DRY RUN" if dry_run else "WRITE",
            item["product_title"],
            alt_text,
        )

        if dry_run:
            skipped += 1
            results.append({**item, "generated_alt": alt_text, "status": "dry_run"})
        else:
            try:
                shopify.update_product_image_alt(
                    product_id=item["product_id"],
                    image_id=item["image_id"],
                    alt_text=alt_text,
                )
                updated += 1
                results.append({**item, "generated_alt": alt_text, "status": "updated"})
            except Exception as e:
                logger.error(
                    "[vision_agent] Shopify write failed for image %s: %s",
                    item["image_id"], e
                )
                errors += 1
                results.append({**item, "generated_alt": alt_text, "status": "error", "error": str(e)})

    summary = {
        "total_images": total_images,
        "missing_alt":  len(missing),
        "updated":      updated,
        "skipped":      skipped,
        "errors":       errors,
        "dry_run":      dry_run,
        "results":      results,
    }
    logger.info("[vision_agent] Alt text audit complete: %s", summary)
    return summary


def run_quality_audit() -> dict:
    """
    Check all product images for photography quality issues.
    READ ONLY — never writes to Shopify.

    Returns: {total_images, issues_found, report: [{product, image, score, action}]}
    """
    vision = NvidiaVisionModule()
    logger.info("[vision_agent] Starting image quality audit (read-only)")

    raw      = shopify._get("/products.json", {"limit": 250, "fields": "id,title,images"})
    products = raw.get("products", [])
    report   = []
    issues   = 0
    total    = 0

    for product in products:
        title  = product.get("title", "")
        images = product.get("images", [])
        for img in images:
            total += 1
            url = img["src"]
            try:
                result = vision.check_image_quality(url)
                score  = result.get("score") or 0
                action = result.get("recommended_action", "")
                if score < 80:
                    issues += 1
                    report.append({
                        "product_title":      title,
                        "image_url":          url,
                        "score":              score,
                        "clean_background":   result.get("clean_background"),
                        "centered_subject":   result.get("centered_subject"),
                        "well_lit":           result.get("well_lit"),
                        "recommended_action": action,
                    })
            except Exception as e:
                logger.error("[vision_agent] Quality check failed for %s: %s", url, e)

    return {
        "total_images": total,
        "issues_found": issues,
        "report":       report,
    }


def run_description_gen(product_ids: list, dry_run: bool = DRY_RUN) -> dict:
    """
    Generate product descriptions for given product IDs using vision model.
    Writes to Shopify body_html unless dry_run=True.
    """
    vision  = NvidiaVisionModule()
    results = []

    for pid in product_ids:
        try:
            product = shopify.get_product(pid).get("product", {})
            images  = product.get("images", [])
            if not images:
                results.append({"product_id": pid, "status": "skipped", "reason": "no images"})
                continue

            image_url   = images[0]["src"]
            description = vision.describe_product(image_url)

            if dry_run:
                results.append({
                    "product_id":  pid,
                    "title":       product.get("title"),
                    "description": description,
                    "status":      "dry_run",
                })
            else:
                shopify.update_product(pid, {"body_html": f"<p>{description}</p>"})
                results.append({
                    "product_id":  pid,
                    "title":       product.get("title"),
                    "description": description,
                    "status":      "updated",
                })
        except Exception as e:
            logger.error("[vision_agent] Description gen failed for product %d: %s", pid, e)
            results.append({"product_id": pid, "status": "error", "error": str(e)})

    return {"dry_run": dry_run, "results": results}
