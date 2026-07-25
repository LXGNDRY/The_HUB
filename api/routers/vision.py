"""
api/routers/vision.py — NVIDIA NIM Vision API Routes

Exposes vision agent workflows as REST endpoints on The HUB API.

Endpoints:
  POST /api/vision/alt-text/audit     — Run alt text audit (dry_run=true by default)
  POST /api/vision/alt-text/apply     — Run alt text audit with dry_run=false (writes to Shopify)
  POST /api/vision/quality/audit      — Run product image quality audit (read-only)
  POST /api/vision/descriptions/gen   — Generate descriptions for given product IDs
  GET  /api/vision/status             — Health check + model info
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from agents.vision_agent import (
    run_alt_text_audit,
    run_quality_audit,
    run_description_gen,
)

logger = logging.getLogger("gcp-bot.routers.vision")
router = APIRouter()


# ─────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────

class AltTextRequest(BaseModel):
    dry_run: bool = True
    force_overwrite: bool = False


class DescriptionRequest(BaseModel):
    product_ids: list[int]
    dry_run: bool = True


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@router.get("/status")
def vision_status():
    """Health check — confirms NVIDIA NIM module is reachable."""
    import os
    key_set = bool(os.getenv("NVIDIA_API_KEY"))
    return {
        "status":  "ok" if key_set else "misconfigured",
        "model":   os.getenv("NVIDIA_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct"),
        "api_key": "set" if key_set else "MISSING — add NVIDIA_API_KEY to Cloud Run env",
    }


@router.post("/alt-text/audit", )
def alt_text_audit(req: AltTextRequest):
    """
    Audit all product images for missing alt text.
    dry_run=true (default): preview only, no Shopify writes.
    dry_run=false: writes alt text to Shopify.
    """
    try:
        result = run_alt_text_audit(dry_run=req.dry_run)
        return result
    except Exception as e:
        logger.error("[vision/alt-text/audit] %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alt-text/apply", )
def alt_text_apply():
    """
    Apply alt text to all products missing it. Writes directly to Shopify.
    Shorthand for dry_run=false.
    """
    try:
        result = run_alt_text_audit(dry_run=False)
        return result
    except Exception as e:
        logger.error("[vision/alt-text/apply] %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quality/audit", )
def quality_audit():
    """
    Audit all product images for photography quality issues.
    Read-only — never writes to Shopify.
    """
    try:
        result = run_quality_audit()
        return result
    except Exception as e:
        logger.error("[vision/quality/audit] %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/descriptions/gen", )
def descriptions_gen(req: DescriptionRequest):
    """
    Generate product descriptions for given product IDs.
    dry_run=true (default): preview only.
    dry_run=false: writes body_html to Shopify.
    """
    if not req.product_ids:
        raise HTTPException(status_code=400, detail="product_ids cannot be empty")
    try:
        result = run_description_gen(req.product_ids, dry_run=req.dry_run)
        return result
    except Exception as e:
        logger.error("[vision/descriptions/gen] %s", e)
        raise HTTPException(status_code=500, detail=str(e))
