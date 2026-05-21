"""
api/routers/gemini.py — Gemini API endpoints

Routes:
  POST /api/gemini/generate               — Raw prompt generation
  POST /api/gemini/product-description    — Generate product description
  POST /api/gemini/seo-meta               — Generate SEO meta tags
  POST /api/gemini/social-caption         — Generate social media caption
  POST /api/gemini/blog-outline           — Generate blog post outline
  GET  /api/gemini/daily-quote            — Generate today's brand quote
  POST /api/gemini/analyze-seo            — AI SEO analysis from GSC+GA4 data
  GET  /api/gemini/models                 — List available Gemini models
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("gcp-bot.api.gemini")
router = APIRouter()


# ------------------------------------------------------------------
# Request/response models
# ------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str
    temperature: float = 0.7
    max_tokens: int = 1024


class ProductDescRequest(BaseModel):
    product_name: str
    keywords: Optional[list[str]] = None
    tone: str = "premium"


class SeoMetaRequest(BaseModel):
    page_title: str
    page_type: str = "product"


class SocialCaptionRequest(BaseModel):
    product_name: str
    platform: str = "instagram"
    tone: str = "streetwear"


class BlogOutlineRequest(BaseModel):
    topic: str
    target_keywords: Optional[list[str]] = None


class AnalyzeSeoRequest(BaseModel):
    gsc_data: dict
    ga4_data: dict


# ------------------------------------------------------------------
# Module factory
# ------------------------------------------------------------------

def _get_module():
    try:
        from modules.gemini import GeminiModule
        return GeminiModule()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Gemini unavailable: {e}")
    except Exception as e:
        logger.error("[gemini router] Module init failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/generate")
def generate_text(body: GenerateRequest):
    """Generate text from a raw prompt."""
    gem = _get_module()
    try:
        result = gem.generate(body.prompt, temperature=body.temperature, max_tokens=body.max_tokens)
        return {"result": result, "prompt_length": len(body.prompt)}
    except Exception as e:
        logger.error("[gemini] generate failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/product-description")
def product_description(body: ProductDescRequest):
    """Generate a Shopify product description optimised for SEO."""
    gem = _get_module()
    try:
        result = gem.generate_product_description(
            body.product_name,
            keywords=body.keywords,
            tone=body.tone,
        )
        return {"product_name": body.product_name, "description": result}
    except Exception as e:
        logger.error("[gemini] product-description failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seo-meta")
def seo_meta(body: SeoMetaRequest):
    """Generate SEO meta title and description for a page."""
    gem = _get_module()
    try:
        result = gem.generate_seo_meta(body.page_title, body.page_type)
        return result
    except Exception as e:
        logger.error("[gemini] seo-meta failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/social-caption")
def social_caption(body: SocialCaptionRequest):
    """Generate a platform-specific social media caption."""
    gem = _get_module()
    try:
        result = gem.generate_social_caption(
            body.product_name,
            platform=body.platform,
            tone=body.tone,
        )
        return {"product_name": body.product_name, "platform": body.platform, "caption": result}
    except Exception as e:
        logger.error("[gemini] social-caption failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/blog-outline")
def blog_outline(body: BlogOutlineRequest):
    """Generate a full SEO blog post outline."""
    gem = _get_module()
    try:
        result = gem.generate_blog_outline(body.topic, body.target_keywords)
        return {"topic": body.topic, "outline": result}
    except Exception as e:
        logger.error("[gemini] blog-outline failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-quote")
def daily_quote(theme: str = "motivation", brand_voice: str = "streetwear"):
    """Generate today's brand quote for social posting."""
    gem = _get_module()
    try:
        result = gem.generate_daily_quote(theme=theme, brand_voice=brand_voice)
        return {"quote": result, "theme": theme}
    except Exception as e:
        logger.error("[gemini] daily-quote failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-seo")
def analyze_seo(body: AnalyzeSeoRequest):
    """Use AI to generate actionable SEO insights from GSC + GA4 data."""
    gem = _get_module()
    try:
        result = gem.analyze_seo_data(body.gsc_data, body.ga4_data)
        return {"analysis": result}
    except Exception as e:
        logger.error("[gemini] analyze-seo failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
def list_models():
    """List available Gemini models."""
    gem = _get_module()
    try:
        models = gem.list_models()
        return {"models": models, "count": len(models)}
    except Exception as e:
        logger.error("[gemini] list-models failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
