"""
Klaviyo router — Email & SMS marketing API.
Prefix in main.py: /api/klaviyo

Endpoints:
  GET  /overview              — account summary (lists, campaigns, metrics)
  GET  /account               — account info
  GET  /profiles              — list profiles (page_size query param)
  GET  /profiles/{id}         — get single profile
  GET  /profiles/search       — find profile by email (?email=...)
  GET  /lists                 — all lists
  GET  /lists/{id}/profiles   — members of a list
  GET  /campaigns             — all campaigns (?channel=email|sms)
  GET  /metrics               — all metrics
  POST /events                — track a custom event
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("gcp-bot.klaviyo")
router = APIRouter()


def _module():
    from modules.klaviyo import KlaviyoModule
    return KlaviyoModule()


# ── Request models ──────────────────────────────────────────────────────────

class EventRequest(BaseModel):
    event_name: str
    email: str
    properties: Optional[dict] = None


# ── Routes ──────────────────────────────────────────────────────────────────

@router.get("/overview", summary="Klaviyo account overview")
def klaviyo_overview():
    """Account summary — lists, recent campaigns, metrics count."""
    try:
        return _module().get_overview()
    except Exception as exc:
        logger.error("klaviyo overview error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/account", summary="Klaviyo account info")
def klaviyo_account():
    try:
        return _module().get_account()
    except Exception as exc:
        logger.error("klaviyo account error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/profiles", summary="List Klaviyo profiles")
def klaviyo_profiles(page_size: int = Query(50, ge=1, le=100)):
    try:
        return _module().list_profiles(page_size=page_size)
    except Exception as exc:
        logger.error("klaviyo profiles error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/profiles/search", summary="Find profile by email")
def klaviyo_search_profile(email: str = Query(..., description="Email address to search")):
    try:
        return _module().search_profile_by_email(email)
    except Exception as exc:
        logger.error("klaviyo search profile error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/profiles/{profile_id}", summary="Get single Klaviyo profile")
def klaviyo_get_profile(profile_id: str):
    try:
        return _module().get_profile(profile_id)
    except Exception as exc:
        logger.error("klaviyo get profile error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/lists", summary="List all Klaviyo lists")
def klaviyo_lists():
    try:
        return _module().list_lists()
    except Exception as exc:
        logger.error("klaviyo lists error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/lists/{list_id}/profiles", summary="Get profiles in a Klaviyo list")
def klaviyo_list_profiles(
    list_id: str,
    page_size: int = Query(50, ge=1, le=100),
):
    try:
        return _module().get_list_profiles(list_id, page_size=page_size)
    except Exception as exc:
        logger.error("klaviyo list profiles error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/campaigns", summary="List Klaviyo campaigns")
def klaviyo_campaigns(channel: str = Query("email", description="email or sms")):
    try:
        return _module().list_campaigns(channel=channel)
    except Exception as exc:
        logger.error("klaviyo campaigns error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/metrics", summary="List all Klaviyo metrics")
def klaviyo_metrics():
    try:
        return _module().list_metrics()
    except Exception as exc:
        logger.error("klaviyo metrics error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/events", summary="Track a custom Klaviyo event")
def klaviyo_track_event(body: EventRequest):
    """
    Track a custom event for a profile.
    Example: Placed Order, Viewed Product, Abandoned Cart
    """
    try:
        return _module().create_event(
            event_name=body.event_name,
            email=body.email,
            properties=body.properties,
        )
    except Exception as exc:
        logger.error("klaviyo track event error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
