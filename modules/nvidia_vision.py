"""
modules/nvidia_vision.py — NVIDIA NIM Vision Language Model Module

Provides vision-powered product analysis for The HUB using NVIDIA's
hosted NIM serverless API (Llama 3.2 11B Vision Instruct).

Capabilities:
  - generate_alt_text(image_url)      → SEO-optimised alt text string
  - describe_product(image_url)       → Full product description paragraph
  - check_image_quality(image_url)    → Quality audit dict (clean/centered/lit)
  - batch_alt_text(image_urls)        → List of alt text strings (rate-limited)

Auth: NVIDIA_API_KEY env var (nvapi-... key from build.nvidia.com)
Model: meta/llama-3.2-11b-vision-instruct (OpenAI-compatible endpoint)
Rate limit: 40 RPM free tier — batch jobs use 1.5s sleep between calls.

Brand voice: Bold, confident, streetwear. No em dashes. No excessive title case.
"""

import os
import time
import logging
import base64
from typing import Optional
from io import BytesIO

import requests

logger = logging.getLogger("gcp-bot.nvidia_vision")

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
NVIDIA_API_KEY  = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
VISION_MODEL    = os.getenv("NVIDIA_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct")

# Free tier: 40 RPM → 1 req/1.5s to stay safe
RATE_LIMIT_SLEEP = float(os.getenv("NVIDIA_RATE_LIMIT_SLEEP", "1.5"))

# Brand context injected into every prompt
BRAND_CONTEXT = (
    "You are writing for Legendary Branding — a bold, confident streetwear brand. "
    "Voice: direct, emotionally resonant, no em dashes, no excessive title case on body copy. "
    "Key product line: Neverdy (Never Die) Collection — 400GSM luxury cotton hoodies."
)


# ─────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────
class NvidiaVisionModule:
    """
    Wrapper around NVIDIA NIM Vision Language Model API.
    Uses OpenAI-compatible /chat/completions endpoint with image_url content blocks.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or NVIDIA_API_KEY
        if not self.api_key:
            raise RuntimeError(
                "NVIDIA_API_KEY is not set. Add it to Cloud Run env vars and GitHub secrets."
            )
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _chat(self, prompt: str, image_url: str, max_tokens: int = 256) -> str:
        """
        Core chat completion call with a single image + text prompt.
        Handles 429 rate-limit with exponential backoff (3 attempts).
        """
        payload = {
            "model": VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "top_p": 0.7,
        }

        for attempt in range(3):
            resp = self.session.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                json=payload,
                timeout=30,
            )
            if resp.status_code == 429:
                wait = 20 * (attempt + 1)
                logger.warning(
                    "[nvidia_vision] 429 rate-limited — retrying in %ds (attempt %d/3)", wait, attempt + 1
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break

        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    # ─────────────────────────────────────────
    # Public methods
    # ─────────────────────────────────────────

    def generate_alt_text(self, image_url: str) -> str:
        """
        Generate a concise, SEO-optimised alt text string for a product image.
        Target: 10-15 words, describes what's visible, includes brand when relevant.
        """
        prompt = (
            f"{BRAND_CONTEXT}\n\n"
            "Look at this product image and write a concise alt text description "
            "for use on an e-commerce product page (for SEO and accessibility). "
            "Requirements: 10-15 words max, describe what is visually present "
            "(garment type, color, key details), do not start with 'Image of' or 'Photo of', "
            "do not include price or availability. "
            "Return ONLY the alt text string, nothing else."
        )
        result = self._chat(prompt, image_url, max_tokens=60)
        # Strip quotes if model wraps output
        return result.strip('"').strip("'")

    def describe_product(self, image_url: str) -> str:
        """
        Generate a full product description paragraph from a product image.
        Brand voice: bold, confident, streetwear. ~50-80 words.
        """
        prompt = (
            f"{BRAND_CONTEXT}\n\n"
            "Look at this product image and write a compelling product description paragraph "
            "for use on a Shopify product page. "
            "Requirements: 50-80 words, brand voice (bold, confident, streetwear), "
            "highlight visible design details, fabric feel, and cultural resonance. "
            "No em dashes. No excessive title case on body copy. "
            "Return ONLY the description paragraph, nothing else."
        )
        return self._chat(prompt, image_url, max_tokens=150)

    def check_image_quality(self, image_url: str) -> dict:
        """
        Audit a product image for e-commerce quality standards.
        Returns a dict with keys: clean_background, centered_subject,
        well_lit, recommended_action, score (0-100).
        """
        prompt = (
            "You are a product photography QA inspector for an e-commerce brand. "
            "Evaluate this product image on these criteria:\n"
            "1. clean_background: Is the background clean/white/neutral? (true/false)\n"
            "2. centered_subject: Is the product centered and fully visible? (true/false)\n"
            "3. well_lit: Is the image well-lit with no harsh shadows? (true/false)\n"
            "4. score: Overall quality score 0-100\n"
            "5. recommended_action: One sentence on what to fix, or 'No action needed'\n\n"
            "Return ONLY valid JSON with those exact 5 keys."
        )
        raw = self._chat(prompt, image_url, max_tokens=120)
        try:
            import json
            # Strip markdown code fences if present
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except Exception:
            logger.warning("[nvidia_vision] JSON parse failed for quality check: %s", raw)
            return {
                "clean_background": None,
                "centered_subject": None,
                "well_lit": None,
                "score": None,
                "recommended_action": raw,
            }

    def batch_alt_text(self, image_urls: list[str]) -> list[dict]:
        """
        Generate alt text for a list of image URLs.
        Respects 40 RPM free tier with RATE_LIMIT_SLEEP between calls.

        Returns list of dicts: {url, alt_text, error}
        """
        results = []
        total = len(image_urls)
        for i, url in enumerate(image_urls, 1):
            logger.info("[nvidia_vision] Alt text %d/%d: %s", i, total, url)
            try:
                alt = self.generate_alt_text(url)
                results.append({"url": url, "alt_text": alt, "error": None})
            except Exception as e:
                logger.error("[nvidia_vision] Failed on %s: %s", url, e)
                results.append({"url": url, "alt_text": None, "error": str(e)})
            if i < total:
                time.sleep(RATE_LIMIT_SLEEP)
        return results
