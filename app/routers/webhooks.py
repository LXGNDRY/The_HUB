"""Provider webhooks. Every route verifies the unmodified request body."""

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.core.config import settings
from app.core.security import verify_shopify_webhook
from app.core.webhooks import InMemoryEventStore, verify_hex_signature

router = APIRouter()
events = InMemoryEventStore()


@router.post("/shopify")
async def shopify_webhook(
    request: Request,
    x_shopify_hmac_sha256: str = Header(default=""),
    x_shopify_webhook_id: str = Header(default=""),
    x_shopify_topic: str = Header(default="unknown"),
):
    body = await request.body()
    if not verify_shopify_webhook(body, x_shopify_hmac_sha256, settings.SHOPIFY_CLIENT_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Shopify signature.")
    if not x_shopify_webhook_id:
        raise HTTPException(status_code=400, detail="Missing Shopify webhook ID.")
    claimed = await events.claim("shopify", x_shopify_webhook_id)
    return {"received": True, "duplicate": not claimed, "topic": x_shopify_topic}


@router.post("/razorpay")
async def razorpay_webhook(request: Request, x_razorpay_signature: str = Header(default="")):
    body = await request.body()
    if not verify_hex_signature(body, x_razorpay_signature, settings.RAZORPAY_WEBHOOK_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Razorpay signature.")
    event_id = request.headers.get("X-Razorpay-Event-Id", x_razorpay_signature)
    claimed = await events.claim("razorpay", event_id)
    return {"received": True, "duplicate": not claimed}


@router.post("/stripe")
async def stripe_webhook(request: Request):
    # Stripe verification requires stripe.Webhook.construct_event with the raw body.
    # Until the durable event handler is implemented, fail closed instead of acknowledging forged events.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Stripe webhook processing is quarantined pending verified durable handling.",
    )
