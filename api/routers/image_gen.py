"""
api/routers/image_gen.py — NVIDIA Image Generation Routes

Endpoints:
  POST /api/image-gen/generate  — Generate an image from a text prompt; returns PNG
  GET  /api/image-gen/status    — Health check + model info
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional

from modules.nvidia_image_gen import NvidiaImageGenModule

logger = logging.getLogger("gcp-bot.routers.image_gen")
router = APIRouter()


class ImageGenRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    negative_prompt: Optional[str] = ""
    width: Optional[int] = 1024
    height: Optional[int] = 1024
    cfg_scale: Optional[float] = 7.0
    steps: Optional[int] = 25
    seed: Optional[int] = 0


@router.get("/status")
def image_gen_status():
    import os
    key_set = bool(os.getenv("NVIDIA_API_KEY"))
    return {
        "status": "ok" if key_set else "misconfigured",
        "model": "stabilityai/stable-diffusion-xl-base-1.0",
        "api_key": "set" if key_set else "MISSING — add NVIDIA_API_KEY to Cloud Run env",
    }


@router.post("/generate")
def generate_image(req: ImageGenRequest):
    """
    Generate an image from a text prompt using NVIDIA Stable Diffusion XL.
    Returns the image as PNG bytes (Content-Type: image/png).
    """
    try:
        client = NvidiaImageGenModule()
        img_bytes = client.generate(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt or "",
            width=req.width,
            height=req.height,
            cfg_scale=req.cfg_scale,
            steps=req.steps,
            seed=req.seed,
        )
        return Response(content=img_bytes, media_type="image/png")
    except RuntimeError as e:
        logger.error("[image-gen/generate] %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("[image-gen/generate] unexpected error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
