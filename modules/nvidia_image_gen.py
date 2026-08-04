"""
modules/nvidia_image_gen.py — NVIDIA NIM Image Generation Module

Generates images via NVIDIA's hosted Stable Diffusion XL API.

Capabilities:
  - generate(prompt, **kwargs) → raw PNG bytes

Auth: NVIDIA_API_KEY env var (nvapi-... key from build.nvidia.com)
Model: stabilityai/stable-diffusion-xl-base-1.0
"""

import os
import base64
import logging
import requests

logger = logging.getLogger("gcp-bot.nvidia_image_gen")

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_IMGGEN_URL = "https://ai.api.nvidia.com/v1/genai/stabilityai/stable-diffusion-xl-base-1.0"


class NvidiaImageGenModule:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or NVIDIA_API_KEY
        if not self.api_key:
            raise RuntimeError(
                "NVIDIA_API_KEY is not set. Add it to Cloud Run env vars."
            )
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        cfg_scale: float = 7.0,
        steps: int = 25,
        seed: int = 0,
    ) -> bytes:
        """
        Generate an image from a text prompt.
        Returns raw PNG bytes.
        """
        payload = {
            "text_prompts": [{"text": prompt, "weight": 1}],
            "cfg_scale": cfg_scale,
            "sampler": "K_DPM_2_ANCESTRAL",
            "seed": seed,
            "steps": steps,
            "width": width,
            "height": height,
        }
        if negative_prompt:
            payload["text_prompts"].append({"text": negative_prompt, "weight": -1})

        logger.info("[nvidia_image_gen] Generating image for prompt: %.80s", prompt)
        resp = self.session.post(NVIDIA_IMGGEN_URL, json=payload, timeout=120)
        resp.raise_for_status()

        data = resp.json()
        artifacts = data.get("artifacts", [])
        if not artifacts:
            raise RuntimeError(f"No artifacts in NVIDIA response: {data}")

        img_bytes = base64.b64decode(artifacts[0]["base64"])
        logger.info("[nvidia_image_gen] Image generated (%d bytes)", len(img_bytes))
        return img_bytes
