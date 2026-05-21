"""
modules/higgsfield.py — Higgsfield AI Module

Provides AI-powered image and video generation for the GCP Bot using
the Higgsfield platform API (platform.higgsfield.ai).

Supports:
  - Text-to-image generation (Soul, Reve, and any model on the platform)
  - Image-to-video generation (DoP, Kling, Seedance, and more)
  - Async polling for generation status
  - Webhook support for production workflows

Auth: Authorization: Key {key_id}:{key_secret}
Docs: https://docs.higgsfield.ai/docs/how-to/introduction.md
"""

import os
import time
import logging
import requests
from typing import Optional

logger = logging.getLogger("gcp-bot.higgsfield")

HIGGSFIELD_API_KEY_ID = os.getenv("HIGGSFIELD_API_KEY_ID", "")
HIGGSFIELD_API_KEY_SECRET = os.getenv("HIGGSFIELD_API_KEY_SECRET", "")
HIGGSFIELD_BASE_URL = "https://platform.higgsfield.ai"

# Default models
DEFAULT_IMAGE_MODEL = "higgsfield-ai/soul/standard"
DEFAULT_VIDEO_MODEL = "higgsfield-ai/dop/standard"

# Poll settings
POLL_INTERVAL_SEC = 5
POLL_TIMEOUT_SEC = 300


class HiggsfieldModule:
    """
    Wrapper around the Higgsfield platform API.
    Handles async generation with optional polling.
    """

    def __init__(self, key_id: str = None, key_secret: str = None):
        self.key_id = key_id or HIGGSFIELD_API_KEY_ID
        self.key_secret = key_secret or HIGGSFIELD_API_KEY_SECRET
        if not self.key_id or not self.key_secret:
            raise ValueError(
                "Higgsfield credentials not configured. "
                "Set HIGGSFIELD_API_KEY_ID and HIGGSFIELD_API_KEY_SECRET env vars."
            )
        self.auth_header = f"Key {self.key_id}:{self.key_secret}"

    def _headers(self) -> dict:
        return {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Core submission
    # ------------------------------------------------------------------

    def submit(self, model_id: str, payload: dict) -> dict:
        """
        Submit a generation request to the Higgsfield queue.
        Returns the queued response with request_id and status_url.
        """
        url = f"{HIGGSFIELD_BASE_URL}/{model_id}"
        logger.info("[higgsfield] Submitting to model=%s payload_keys=%s", model_id, list(payload.keys()))
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(
                f"Higgsfield submit failed: HTTP {resp.status_code} — {resp.text[:300]}"
            )
        return resp.json()

    def get_status(self, request_id: str) -> dict:
        """
        Poll the status of a generation request.
        Returns the full status response (queued / in_progress / completed / failed / nsfw).
        """
        url = f"{HIGGSFIELD_BASE_URL}/requests/{request_id}/status"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Higgsfield status check failed: HTTP {resp.status_code} — {resp.text[:200]}"
            )
        return resp.json()

    def cancel(self, request_id: str) -> dict:
        """Cancel a queued (not yet in-progress) request."""
        url = f"{HIGGSFIELD_BASE_URL}/requests/{request_id}/cancel"
        resp = requests.post(url, headers=self._headers(), timeout=15)
        if resp.status_code not in (200, 202):
            raise RuntimeError(
                f"Higgsfield cancel failed: HTTP {resp.status_code} — {resp.text[:200]}"
            )
        return {"status": "cancelled", "request_id": request_id}

    # ------------------------------------------------------------------
    # Polling helper
    # ------------------------------------------------------------------

    def wait_for_completion(
        self, request_id: str, timeout: int = POLL_TIMEOUT_SEC, interval: int = POLL_INTERVAL_SEC
    ) -> dict:
        """
        Poll until status is completed, failed, or nsfw.
        Raises TimeoutError if timeout exceeded.
        """
        elapsed = 0
        while elapsed < timeout:
            result = self.get_status(request_id)
            status = result.get("status", "")
            logger.info("[higgsfield] request_id=%s status=%s elapsed=%ds", request_id, status, elapsed)
            if status in ("completed", "failed", "nsfw"):
                return result
            time.sleep(interval)
            elapsed += interval
        raise TimeoutError(
            f"Higgsfield generation timed out after {timeout}s for request_id={request_id}"
        )

    # ------------------------------------------------------------------
    # High-level methods
    # ------------------------------------------------------------------

    def generate_image(
        self,
        prompt: str,
        model_id: str = DEFAULT_IMAGE_MODEL,
        aspect_ratio: str = "1:1",
        resolution: str = "720p",
        wait: bool = True,
        webhook_url: Optional[str] = None,
    ) -> dict:
        """
        Generate an image from a text prompt.

        If wait=True (default), polls until complete and returns the result.
        If wait=False, returns the queued response immediately.
        Optionally pass a webhook_url for async callback instead of polling.
        """
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }
        headers_extra = {}
        if webhook_url:
            headers_extra["X-Webhook-URL"] = webhook_url

        url = f"{HIGGSFIELD_BASE_URL}/{model_id}"
        logger.info("[higgsfield] Image gen: model=%s prompt=%s...", model_id, prompt[:60])
        h = {**self._headers(), **headers_extra}
        resp = requests.post(url, headers=h, json=payload, timeout=30)
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(f"Higgsfield image submit failed: HTTP {resp.status_code} — {resp.text[:300]}")
        queued = resp.json()

        if webhook_url or not wait:
            return queued

        request_id = queued.get("request_id")
        if not request_id:
            return queued
        return self.wait_for_completion(request_id)

    def generate_video(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        model_id: str = DEFAULT_VIDEO_MODEL,
        duration: int = 5,
        aspect_ratio: Optional[str] = None,
        wait: bool = True,
        webhook_url: Optional[str] = None,
    ) -> dict:
        """
        Generate a video.

        If image_url is provided → image-to-video.
        Otherwise → text-to-video.

        If wait=True (default), polls until complete and returns the result.
        Optionally pass a webhook_url for async callback.
        """
        payload: dict = {"prompt": prompt, "duration": duration}
        if image_url:
            payload["image_url"] = image_url
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio

        headers_extra = {}
        if webhook_url:
            headers_extra["X-Webhook-URL"] = webhook_url

        url = f"{HIGGSFIELD_BASE_URL}/{model_id}"
        mode = "image-to-video" if image_url else "text-to-video"
        logger.info("[higgsfield] Video gen (%s): model=%s prompt=%s...", mode, model_id, prompt[:60])
        h = {**self._headers(), **headers_extra}
        resp = requests.post(url, headers=h, json=payload, timeout=30)
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(f"Higgsfield video submit failed: HTTP {resp.status_code} — {resp.text[:300]}")
        queued = resp.json()

        if webhook_url or not wait:
            return queued

        request_id = queued.get("request_id")
        if not request_id:
            return queued
        return self.wait_for_completion(request_id)

    def generate_soul_video(
        self,
        prompt: str,
        reference_image_urls: list,
        model_id: str = "higgsfield-ai/soul/standard",
        wait: bool = True,
    ) -> dict:
        """
        Soul mode: generate a video with character reference images.
        Pass 1-3 reference_image_urls for character consistency.
        """
        payload = {
            "prompt": prompt,
            "reference_image_urls": reference_image_urls,
        }
        url = f"{HIGGSFIELD_BASE_URL}/{model_id}"
        logger.info("[higgsfield] Soul mode: model=%s refs=%d prompt=%s...", model_id, len(reference_image_urls), prompt[:60])
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(f"Higgsfield soul submit failed: HTTP {resp.status_code} — {resp.text[:300]}")
        queued = resp.json()

        if not wait:
            return queued
        request_id = queued.get("request_id")
        if not request_id:
            return queued
        return self.wait_for_completion(request_id)
