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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiModule:
    """
    Wrapper around the Gemini REST API.
    Uses google-generativeai SDK if available, falls back to REST.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or GOOGLE_API_KEY
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not set. Cannot use GeminiModule.")
        self._sdk_client = None
        self._init_sdk()

    def _init_sdk(self):
        """Try to initialise the google-generativeai SDK."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._sdk_client = genai.GenerativeModel(GEMINI_MODEL)
            logger.info("[gemini] SDK client initialised with model=%s", GEMINI_MODEL)
        except ImportError:
            logger.info("[gemini] SDK not installed — using REST fallback.")
        except Exception as e:
            logger.warning("[gemini] SDK init failed (%s) — using REST fallback.", e)

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """
        Generate text from a prompt.

        Args:
            prompt:       The user prompt / instruction.
            temperature:  Creativity level 0.0–1.0 (default 0.7).
            max_tokens:   Max output tokens (default 1024).

        Returns:
            Generated text string.
        """
        if self._sdk_client:
            return self._generate_sdk(prompt, temperature, max_tokens)
        return self._generate_rest(prompt, temperature, max_tokens)

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
            "contents": [{"parts": [{"text": prompt}]}],
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
            f"Do not use generic filler phrases. Make it feel real and brand-aligned."
        )
        logger.info("[gemini] Generating %s caption for: %s", platform, product_name)
        return self.generate(prompt, temperature=0.85)

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
            f"Write one short, punchy {theme} quote suitable for a {brand_voice} brand's daily social post.\n"
            f"Brand: Legendary Branding.\n"
            f"Requirements:\n"
            f"- 1-2 lines max\n"
            f"- No quotation marks around it\n"
            f"- Bold, memorable, authentic to the brand\n"
            f"- Do NOT include hashtags or attribution\n"
            f"Return ONLY the quote text, nothing else."
        )
        return self.generate(prompt, temperature=0.9, max_tokens=100)

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
