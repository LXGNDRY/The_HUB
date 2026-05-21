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
# Module singleton — instantiated once per Cloud Run instance so the
# SA credentials object and token cache persist across requests.
# ------------------------------------------------------------------

_gemini_module = None

def _get_module():
    global _gemini_module
    if _gemini_module is not None:
        return _gemini_module
    try:
        from modules.gemini import GeminiModule
        from auth.credentials import get_credentials
        _gemini_module = GeminiModule(credentials=get_credentials())
        return _gemini_module
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
        error_str = str(e)
        # Provide actionable fix instructions for the two known auth failure modes
        if "API_KEY_SERVICE_BLOCKED" in error_str:
            return {
                "status": "setup_required",
                "error": "GOOGLE_API_KEY is restricted and does not allow generativelanguage.googleapis.com",
                "fix": (
                    "Go to https://console.cloud.google.com/apis/credentials?project=idx-lngndny, "
                    "find the API key, and either: (A) remove all API restrictions, or "
                    "(B) add 'Generative Language API' to the allowed APIs list."
                ),
                "or_grant_iam": (
                    "Alternatively, grant roles/aiplatform.user to "
                    "901935277314-compute@developer.gserviceaccount.com at "
                    "https://console.cloud.google.com/iam-admin/iam?project=idx-lngndny "
                    "to use Vertex AI instead (more secure, no API key needed)."
                ),
            }
        if "403" in error_str or "aiplatform" in error_str:
            return {
                "status": "setup_required",
                "error": "SA lacks Vertex AI permissions",
                "fix": (
                    "Grant roles/aiplatform.user to "
                    "901935277314-compute@developer.gserviceaccount.com at "
                    "https://console.cloud.google.com/iam-admin/iam?project=idx-lngndny"
                ),
            }
        raise HTTPException(status_code=500, detail=error_str)


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


@router.get("/auth-test")
def auth_test():
    """
    Debug: tests both the low-level Vertex REST call AND the full module.generate() path.
    """
    import os, requests
    import google.auth.transport.requests

    project = os.getenv("GCP_PROJECT_ID", "idx-lngndny")
    region = "us-central1"
    model = "gemini-2.5-flash"

    result = {"low_level": {}, "module_generate": {}, "module_singleton_id": None}

    # --- Low-level test (same as before) ---
    try:
        from auth.credentials import get_credentials
        creds = get_credentials()
        req = google.auth.transport.requests.Request()
        if not creds.valid:
            creds.refresh(req)
        token = creds.token
        url = (
            f"https://{region}-aiplatform.googleapis.com/v1/"
            f"projects/{project}/locations/{region}"
            f"/publishers/google/models/{model}:generateContent"
        )
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"contents": [{"role": "user", "parts": [{"text": "Say 'Legendary' in one word."}]}]},
            timeout=15,
        )
        result["low_level"] = {
            "vertex_status": resp.status_code,
            "text": resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "") if resp.status_code == 200 else resp.text[:200],
        }
    except Exception as e:
        result["low_level"] = {"error": f"{type(e).__name__}: {e}"}

    # --- Module.generate() path (same path as daily-quote) ---
    try:
        gem = _get_module()
        result["module_singleton_id"] = id(gem)
        sa_creds = getattr(gem, '_sa_creds', None)
        result["module_generate"]["sa_creds_present"] = sa_creds is not None
        result["module_generate"]["sa_creds_token"] = bool(getattr(sa_creds, 'token', None)) if sa_creds else False
        # Also expose the token prefix so we can see if it differs from low-level
        try:
            token_preview = gem._get_sa_token()[:20] + "..."
            result["module_generate"]["sa_token_preview"] = token_preview
        except Exception as te:
            result["module_generate"]["sa_token_error"] = str(te)
        # Test Vertex directly using module's token
        try:
            import requests as req_lib
            tok = gem._get_sa_token()
            vurl = f"https://us-central1-aiplatform.googleapis.com/v1/projects/idx-lngndny/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent"
            vr = req_lib.post(vurl, headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, json={"contents": [{"role": "user", "parts": [{"text": "Say Legendary."}]}]}, timeout=15)
            result["module_generate"]["module_vertex_status"] = vr.status_code
            result["module_generate"]["module_vertex_text"] = vr.text[:300]
        except Exception as ve:
            result["module_generate"]["module_vertex_error"] = str(ve)
        text = gem.generate("Say 'Legendary' in one word.", max_tokens=10)
        result["module_generate"]["result"] = text
        result["module_generate"]["status"] = "ok"
    except Exception as e:
        result["module_generate"]["error"] = f"{type(e).__name__}: {e}"
        result["module_generate"]["status"] = "failed"

    return result
