"""Verified, persistently deduplicated provider webhooks."""

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import verify_shopify_webhook
from app.core.webhooks import verify_hex_signature
from app.database import get_db
from app.services.event_store import DatabaseEventStore
from app.services.stripe_service import handle_verified_webhook

router = APIRouter()


@router.post("/shopify")
async def shopify_webhook(
    request: Request,
    x_shopify_hmac_sha256: str = Header(default=""),
    x_shopify_webhook_id: str = Header(default=""),
    x_shopify_topic: str = Header(default="unknown"),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    if not verify_shopify_webhook(body, x_shopify_hmac_sha256, settings.SHOPIFY_CLIENT_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Shopify signature.")
    if not x_shopify_webhook_id:
        raise HTTPException(status_code=400, detail="Missing Shopify webhook ID.")
    claimed = await DatabaseEventStore(db).claim(
        "shopify", x_shopify_webhook_id, x_shopify_topic
    )
    return {"received": True, "duplicate": not claimed, "topic": x_shopify_topic}


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    if not verify_hex_signature(body, x_razorpay_signature, settings.RAZORPAY_WEBHOOK_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Razorpay signature.")
    event_id = request.headers.get("X-Razorpay-Event-Id", x_razorpay_signature)
    claimed = await DatabaseEventStore(db).claim("razorpay", event_id)
    return {"received": True, "duplicate": not claimed}


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            raw_body, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Stripe signature.")
    event_id = str(event.get("id", ""))
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing Stripe event ID.")
    claimed = await DatabaseEventStore(db).claim("stripe", event_id, str(event.get("type", "")))
    if not claimed:
        return {"received": True, "duplicate": True}
    result = await handle_verified_webhook(event, db)
    return {"received": True, "duplicate": False, "result": result}
