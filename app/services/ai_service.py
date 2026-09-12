"""
AI Content service — wraps the existing Gemini and NVIDIA Vision modules.
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class AIContentService:
    """AI-powered content generation using Gemini + NVIDIA Vision."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "")

    def generate_product_description(self, title: str, keywords: str = "") -> str:
        """Generate SEO-optimized product description using Gemini."""
        import modules.gemini as gemini_mod
        gemini = gemini_mod.GeminiModule(api_key=self.api_key)
        prompt = (
            f"Write a compelling SEO product description for: '{title}'. "
            f"Keywords to include: {keywords}. "
            f"Format: 2-3 paragraphs, HTML, include key features and benefits."
        )
        result = gemini.generate(prompt)
        return result

    def generate_seo_meta(self, title: str, description: str) -> dict:
        """Generate SEO title and meta description."""
        import modules.gemini as gemini_mod
        gemini = gemini_mod.GeminiModule(api_key=self.api_key)
        prompt = (
            f"Generate an SEO-optimized meta title (max 60 chars) and meta description "
            f"(max 160 chars) for a product page. Product: '{title}'. "
            f"Description: '{description}'. Return as JSON with keys 'title' and 'description'."
        )
        result = gemini.generate(prompt)
        return {"seo_title": "", "seo_description": ""}  # TODO: parse result

    def generate_alt_text(self, image_url: str) -> str:
        """Generate alt text for a product image using NVIDIA Vision."""
        import modules.nvidia_vision as vision_mod
        return vision_mod.generate_alt_text(image_url)

    def generate_email_template(self, campaign_type: str, brand: str) -> str:
        """Generate Klaviyo email template HTML using Gemini."""
        import modules.gemini as gemini_mod
        gemini = gemini_mod.GeminiModule(api_key=self.api_key)
        prompt = (
            f"Create an HTML email template for a {campaign_type} campaign "
            f"for the brand '{brand}'. Include header, body, CTA button, and footer."
        )
        result = gemini.generate(prompt)
        return result