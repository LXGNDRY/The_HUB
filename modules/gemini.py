"""
modules/gemini.py — Gemini API Module

Provides AI-powered content generation for the GCP Bot using Google's
Gemini 1.5 Flash model. Useful for generating SEO content, product
descriptions, social media captions, and blog post drafts.

Requires: GOOGLE_API_KEY env var (already set in project)
"""

import os
import logging
import json
import requests

logger = logging.getLogger("gcp-bot.gemini")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
# gemini-2.5-flash is the current stable model on Vertex AI (gemini-2.0-flash-001 retired June 2026).
# Use GEMINI_MODEL env var to override without redeploying.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_VERTEX_PROJECT = os.getenv("GCP_PROJECT_ID", "idx-lngndny")
# gemini-2.5-flash is available in us-central1
GEMINI_VERTEX_REGION = os.getenv("GEMINI_VERTEX_REGION", "us-central1")
# Vertex AI REST endpoint — uses SA bearer token, requires roles/aiplatform.user
GEMINI_VERTEX_BASE = (
    f"https://{GEMINI_VERTEX_REGION}-aiplatform.googleapis.com/v1/"
    f"projects/{GEMINI_VERTEX_PROJECT}/locations/{GEMINI_VERTEX_REGION}"
    f"/publishers/google/models"
)


class GeminiModule:
    """
    Wrapper around the Gemini API.
    Auth priority:
      1. Vertex AI SDK with SA credentials (recommended for Cloud Run)
      2. google-generativeai SDK with API key
      3. REST API with API key
    """

    def __init__(self, api_key: str = None, credentials=None):
        self.api_key = api_key or GOOGLE_API_KEY
        self.credentials = credentials
        self._sdk_client = None
        self._vertex_client = None
        self._init_vertex()
        if not self._vertex_client:
            self._init_sdk()

    def _init_vertex(self):
        """
        Verify SA credentials, eagerly fetch the first token at startup.
        Stores the refreshed credentials as self._sa_creds so _get_sa_token()
        reuses the same object (with a valid cached token) on every request.
        """
        if not self.credentials:
            self._sa_ready = False
            self._sa_creds = None
            return
        try:
            import google.auth.transport.requests
            request = google.auth.transport.requests.Request()
            if not self.credentials.valid:
                self.credentials.refresh(request)
            self._sa_creds = self.credentials  # store refreshed creds as the cache object
            self._sa_ready = bool(self.credentials.token)
            if self._sa_ready:
                logger.info(
                    "[gemini] SA token obtained at startup. Expiry: %s",
                    getattr(self.credentials, 'expiry', 'unknown')
                )
        except Exception as e:
            logger.warning("[gemini] SA credential refresh failed (%s) — falling back to API key.", e)
            self._sa_ready = False
            self._sa_creds = None

    def _init_sdk(self):
        """Try google-generativeai SDK with API key."""
        if not self.api_key:
            logger.warning("[gemini] No API key set and Vertex AI unavailable.")
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._sdk_client = genai.GenerativeModel(GEMINI_MODEL)
            logger.info("[gemini] SDK client initialised with model=%s", GEMINI_MODEL)
        except ImportError:
            logger.info("[gemini] google-generativeai SDK not installed — using REST fallback.")
        except Exception as e:
            logger.warning("[gemini] SDK init failed (%s) — using REST fallback.", e)

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """
        Generate text. Always tries Vertex AI first (SA bearer token), no gate.
        Falls back to SDK or REST with API key only on genuine failure.
        """
        try:
            return self._generate_sa_rest(prompt, temperature, max_tokens)
        except Exception as e:
            logger.error("[gemini] Vertex AI path failed (%s: %s) — falling back.", type(e).__name__, str(e)[:120])
        if self._sdk_client:
            try:
                return self._generate_sdk(prompt, temperature, max_tokens)
            except Exception as e:
                logger.error("[gemini] SDK path failed (%s) — trying REST.", str(e)[:80])
        return self._generate_rest(prompt, temperature, max_tokens)

    def _get_sa_token(self) -> str:
        """
        Return a valid SA bearer token for Vertex AI.
        Builds credentials directly from GCP_SA_KEY_JSON env var every time
        (fast — just a JSON parse + conditional HTTPS token fetch).
        Uses cloud-platform scope which covers all GCP APIs including Vertex AI.
        """
        import os, json, datetime
        import google.auth.transport.requests
        from google.oauth2 import service_account

        VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

        # Build or reuse — cache on self, keyed to this scope only
        if not getattr(self, '_sa_creds', None):
            key_json = os.getenv("GCP_SA_KEY_JSON", "")
            if not key_json:
                raise RuntimeError("GCP_SA_KEY_JSON env var not set — cannot authenticate with Vertex AI.")
            info = json.loads(key_json)
            self._sa_creds = service_account.Credentials.from_service_account_info(
                info, scopes=[VERTEX_SCOPE]
            )
            logger.info("[gemini] Built SA credentials from GCP_SA_KEY_JSON.")

        creds = self._sa_creds
        now = datetime.datetime.utcnow()
        expiry = getattr(creds, 'expiry', None)
        needs_refresh = (
            not creds.token
            or expiry is None
            or (expiry - now).total_seconds() < 300
        )
        if needs_refresh:
            req = google.auth.transport.requests.Request()
            creds.refresh(req)
            logger.info("[gemini] SA token refreshed — expiry: %s", getattr(creds, 'expiry', '?'))

        if not creds.token:
            raise RuntimeError("SA token still empty after refresh.")
        return creds.token

    def _generate_sa_rest(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """
        Call Vertex AI REST API authenticated via SA bearer token.
        Endpoint: {region}-aiplatform.googleapis.com/v1/projects/{project}/...
        Requires: roles/aiplatform.user on the SA.
        """
        token = self._get_sa_token()

        # Vertex AI uses a different model path format
        vertex_model = GEMINI_MODEL  # e.g. gemini-2.0-flash
        region = GEMINI_VERTEX_REGION
        project = GEMINI_VERTEX_PROJECT
        url = (
            f"https://{region}-aiplatform.googleapis.com/v1/"
            f"projects/{project}/locations/{region}"
            f"/publishers/google/models/{vertex_model}:generateContent"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        resp = requests.post(url, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _generate_sdk(self, prompt: str, temperature: float, max_tokens: int) -> str:
        import google.generativeai as genai
        config = genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        response = self._sdk_client.generate_content(prompt, generation_config=config)
        return response.text.strip()

    def _generate_rest(self, prompt: str, temperature: float, max_tokens: int) -> str:
        url = f"{GEMINI_BASE_URL}/{GEMINI_MODEL}:generateContent?key={self.api_key}"
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        resp = requests.post(url, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    # ------------------------------------------------------------------
    # High-level helpers for Legendary Branding use cases
    # ------------------------------------------------------------------

    def generate_product_description(self, product_name: str, keywords: list[str] = None, tone: str = "premium") -> str:
        """
        Generate a Shopify product description optimised for SEO.

        Args:
            product_name: e.g. "GOAT Heavyweight Hoodie 460gsm"
            keywords:     SEO keywords to weave in naturally.
            tone:         Writing style — "premium", "streetwear", "minimalist".
        """
        kw_str = ", ".join(keywords) if keywords else "streetwear, premium quality, heavyweight"
        prompt = (
            f"Write a compelling Shopify product description for: {product_name}.\n"
            f"Brand: Legendary Branding — a premium streetwear brand.\n"
            f"Tone: {tone}.\n"
            f"Naturally include these SEO keywords: {kw_str}.\n"
            f"Format: 2-3 short paragraphs + 4 bullet points highlighting key features.\n"
            f"Keep it authentic, not salesy. Under 250 words."
        )
        logger.info("[gemini] Generating product description for: %s", product_name)
        return self.generate(prompt, temperature=0.75)

    def generate_seo_meta(self, page_title: str, page_type: str = "product") -> dict:
        """
        Generate SEO meta title and description for a Shopify page.

        Returns:
            {"meta_title": str, "meta_description": str}
        """
        prompt = (
            f"Generate an SEO meta title and meta description for a Shopify {page_type} page.\n"
            f"Page: {page_title}\n"
            f"Brand: Legendary Branding (premium streetwear).\n"
            f"Rules:\n"
            f"- meta_title: max 60 chars, include primary keyword, brand name at end\n"
            f"- meta_description: 150-160 chars, include CTA, natural keyword placement\n"
            f"Respond ONLY as valid JSON: {{\"meta_title\": \"...\", \"meta_description\": \"...\"}}"
        )
        raw = self.generate(prompt, temperature=0.5, max_tokens=256)
        try:
            # Strip markdown code fences if present
            cleaned = raw.strip().strip("```json").strip("```").strip()
            return json.loads(cleaned)
        except Exception:
            return {"meta_title": raw[:60], "meta_description": raw[60:220]}

    def generate_social_caption(self, product_name: str, platform: str = "instagram", tone: str = "streetwear") -> str:
        """
        Generate a social media caption for a product.

        Args:
            product_name: Product to feature.
            platform:     "instagram" | "facebook" | "twitter"
            tone:         Writing style.
        """
        limits = {"instagram": 2200, "facebook": 500, "twitter": 280}
        char_limit = limits.get(platform, 500)

        prompt = (
            f"Write a {platform} caption for Legendary Branding promoting: {product_name}.\n"
            f"Tone: {tone}, premium, authentic.\n"
            f"Platform: {platform}. Max {char_limit} chars.\n"
            f"Include relevant hashtags at the end (8-12 for Instagram, 3-5 for others).\n"
            f"Do not use generic filler phrases. Make it feel real and brand-aligned.\n"
            f"Return ONLY the caption text itself. No intro, no preamble, no 'Here is a caption:' prefix."
        )
        logger.info("[gemini] Generating %s caption for: %s", platform, product_name)
        return self.generate(prompt, temperature=0.85, max_tokens=512)

    def generate_blog_outline(self, topic: str, target_keywords: list[str] = None) -> str:
        """
        Generate a full blog post outline for SEO content strategy.
        """
        kw_str = ", ".join(target_keywords) if target_keywords else topic
        prompt = (
            f"Create a detailed SEO blog post outline for Legendary Branding's website.\n"
            f"Topic: {topic}\n"
            f"Target keywords: {kw_str}\n"
            f"Format: H1 title + 5-7 H2 sections with 2-3 bullet points each.\n"
            f"Audience: streetwear enthusiasts who care about fabric quality and fit.\n"
            f"Goal: rank on Google, drive organic traffic to product pages."
        )
        logger.info("[gemini] Generating blog outline for: %s", topic)
        return self.generate(prompt, temperature=0.7)

    def generate_daily_quote(self, theme: str = "motivation", brand_voice: str = "streetwear") -> str:
        """
        Generate a short inspirational/brand quote for daily social posting.

        Args:
            theme:       "motivation" | "fashion" | "hustle" | "quality"
            brand_voice: Writing style context.
        """
        prompt = (
            f"You are a copywriter for Legendary Branding, a premium streetwear label.\n"
            f"Write ONE brand quote for today's social post. Theme: {theme}.\n"
            f"\n"
            f"The quote MUST:\n"
            f"- Be a grammatically complete sentence ending with a period or exclamation mark\n"
            f"- Contain between 4 and 8 words (count carefully)\n"
            f"- Sound bold, confident, authentic to {brand_voice} culture\n"
            f"- Contain NO quotation marks, hashtags, or line breaks\n"
            f"\n"
            f"Examples of correct format:\n"
            f"Built different. Worn by legends.\n"
            f"Your style tells the story.\n"
            f"Quality is the only flex that matters.\n"
            f"\n"
            f"Output the quote and nothing else."
        )
        return self.generate(prompt, temperature=0.85, max_tokens=40)

    def analyze_seo_data(self, gsc_data: dict, ga4_data: dict) -> str:
        """
        Use Gemini to generate actionable SEO insights from GSC + GA4 data.

        Args:
            gsc_data: Dict from /api/seo/search-performance endpoint.
            ga4_data: Dict from /api/analytics/traffic endpoint.
        """
        prompt = (
            f"You are an SEO analyst reviewing data for Legendary Branding, a premium streetwear e-commerce store.\n\n"
            f"Google Search Console data (last 28 days):\n{json.dumps(gsc_data, indent=2)}\n\n"
            f"Google Analytics 4 data (last 28 days):\n{json.dumps(ga4_data, indent=2)}\n\n"
            f"Provide:\n"
            f"1. Top 3 actionable SEO opportunities based on this data\n"
            f"2. Any traffic patterns worth noting\n"
            f"3. One quick win to implement this week\n\n"
            f"Be specific and data-driven. Keep it under 300 words."
        )
        logger.info("[gemini] Analyzing SEO data...")
        return self.generate(prompt, temperature=0.4, max_tokens=512)

    # ------------------------------------------------------------------
    # Model info
    # ------------------------------------------------------------------

    def list_models(self) -> list[dict]:
        """List available Gemini models."""
        url = f"{GEMINI_BASE_URL}?key={self.api_key}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "name": m.get("name", ""),
                "display_name": m.get("displayName", ""),
                "description": m.get("description", ""),
                "input_token_limit": m.get("inputTokenLimit"),
                "output_token_limit": m.get("outputTokenLimit"),
            }
            for m in data.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]
