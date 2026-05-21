"""
api/routers/higgsfield.py — Higgsfield AI endpoints

Routes:
  POST /api/higgsfield/generate/image      — Text-to-image generation
  POST /api/higgsfield/generate/video      — Text-to-video OR image-to-video
  POST /api/higgsfield/generate/soul       — Soul mode (character reference video)
  POST /api/higgsfield/submit              — Raw submit (any model, any payload)
  GET  /api/higgsfield/status/{request_id} — Check generation status
  POST /api/higgsfield/cancel/{request_id} — Cancel queued request
  GET  /api/higgsfield/models              — List popular available models
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("gcp-bot.api.higgsfield")
router = APIRouter()


# ------------------------------------------------------------------
# Request/response models
# ------------------------------------------------------------------

class ImageGenerateRequest(BaseModel):
    prompt: str
    model_id: str = "higgsfield-ai/soul/standard"
    aspect_ratio: str = "1:1"
    resolution: str = "720p"
    wait: bool = False          # False = return request_id immediately
    webhook_url: Optional[str] = None


class VideoGenerateRequest(BaseModel):
    prompt: str
    image_url: Optional[str] = None   # if provided → image-to-video; else text-to-video
    model_id: str = "higgsfield-ai/dop/standard"
    duration: int = 5
    aspect_ratio: Optional[str] = None
    wait: bool = False
    webhook_url: Optional[str] = None


class SoulGenerateRequest(BaseModel):
    prompt: str
    reference_image_urls: List[str]
    model_id: str = "higgsfield-ai/soul/standard"
    wait: bool = False


class RawSubmitRequest(BaseModel):
    model_id: str
    payload: dict
    wait: bool = False
    webhook_url: Optional[str] = None


# ------------------------------------------------------------------
# Module singleton
# ------------------------------------------------------------------

_higgsfield_module = None

def _get_module():
    global _higgsfield_module
    if _higgsfield_module is not None:
        return _higgsfield_module
    try:
        from modules.higgsfield import HiggsfieldModule
        _higgsfield_module = HiggsfieldModule()
        return _higgsfield_module
    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"Higgsfield unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Higgsfield init error: {type(e).__name__}: {e}")


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/generate/image")
def generate_image(req: ImageGenerateRequest):
    """
    Generate an image from a text prompt.

    - Default model: higgsfield-ai/soul/standard (flagship)
    - Set wait=false to get request_id immediately, then poll /status/{id}
    - Or pass webhook_url to receive a callback when done
    """
    try:
        mod = _get_module()
        result = mod.generate_image(
            prompt=req.prompt,
            model_id=req.model_id,
            aspect_ratio=req.aspect_ratio,
            resolution=req.resolution,
            wait=req.wait,
            webhook_url=req.webhook_url,
        )
        return {"status": "ok", "result": result}
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("[higgsfield] generate_image error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/generate/video")
def generate_video(req: VideoGenerateRequest):
    """
    Generate a video.

    - If image_url is provided → image-to-video
    - Otherwise → text-to-video
    - Default model: higgsfield-ai/dop/standard
    - Set wait=false to get request_id immediately
    - Popular models: kling-video/v2.1/pro/image-to-video, bytedance/seedance/v1/pro/image-to-video
    """
    try:
        mod = _get_module()
        result = mod.generate_video(
            prompt=req.prompt,
            image_url=req.image_url,
            model_id=req.model_id,
            duration=req.duration,
            aspect_ratio=req.aspect_ratio,
            wait=req.wait,
            webhook_url=req.webhook_url,
        )
        return {"status": "ok", "result": result}
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("[higgsfield] generate_video error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/generate/soul")
def generate_soul(req: SoulGenerateRequest):
    """
    Soul mode: generate a video using character reference images.
    Pass 1-3 publicly accessible image URLs as reference_image_urls.
    Great for consistent character/brand identity in generated videos.
    """
    try:
        mod = _get_module()
        result = mod.generate_soul_video(
            prompt=req.prompt,
            reference_image_urls=req.reference_image_urls,
            model_id=req.model_id,
            wait=req.wait,
        )
        return {"status": "ok", "result": result}
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("[higgsfield] soul generate error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/submit")
def raw_submit(req: RawSubmitRequest):
    """
    Raw submit to any Higgsfield model with custom payload.
    Use this to access models not covered by the high-level endpoints.
    """
    try:
        mod = _get_module()
        queued = mod.submit(req.model_id, req.payload)
        if req.wait:
            request_id = queued.get("request_id")
            if request_id:
                result = mod.wait_for_completion(request_id)
                return {"status": "ok", "result": result}
        return {"status": "ok", "result": queued}
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("[higgsfield] raw_submit error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/status/{request_id}")
def get_status(request_id: str):
    """
    Check the status of a generation request.
    Statuses: queued | in_progress | completed | failed | nsfw
    On completed: result contains images[] and/or video.url
    """
    try:
        mod = _get_module()
        result = mod.get_status(request_id)
        return {"status": "ok", "result": result}
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("[higgsfield] status error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/cancel/{request_id}")
def cancel_request(request_id: str):
    """
    Cancel a queued generation request.
    Only works while status is 'queued' — not once processing has started.
    """
    try:
        mod = _get_module()
        result = mod.cancel(request_id)
        return {"status": "ok", "result": result}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("[higgsfield] cancel error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/models")
def list_models():
    """
    Returns a reference list of popular Higgsfield models.
    For the full catalog visit: https://cloud.higgsfield.ai/explore
    """
    return {
        "status": "ok",
        "models": {
            "image": [
                {"model_id": "higgsfield-ai/soul/standard", "description": "Flagship text-to-image (Soul)"},
                {"model_id": "reve/text-to-image", "description": "Versatile text-to-image"},
            ],
            "video": [
                {"model_id": "higgsfield-ai/dop/standard", "description": "DoP standard image-to-video"},
                {"model_id": "higgsfield-ai/dop/preview", "description": "DoP preview — high quality animation"},
                {"model_id": "kling-video/v2.1/pro/image-to-video", "description": "Kling 2.1 Pro — cinematic"},
                {"model_id": "bytedance/seedance/v1/pro/image-to-video", "description": "Seedance v1 Pro"},
            ],
            "soul_mode": [
                {"model_id": "higgsfield-ai/soul/standard", "description": "Soul standard — character reference video"},
            ],
        },
        "docs": "https://docs.higgsfield.ai",
        "explore": "https://cloud.higgsfield.ai/explore",
    }
