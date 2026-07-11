"""
Webhooks router — receive external webhooks (Shopify, Razorpay, etc).
"""

from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/shopify")
async def shopify_webhook(request: Request):
    """Receive Shopify webhook events (theme deploy, product update, etc)."""
    body = await request.body()
    topic = request.headers.get("X-Shopify-Topic", "unknown")
    # TODO: dispatch to appropriate handler based on topic
    return {"received": True, "topic": topic}


@router.post("/razorpay")
async def razorpay_webhook(request: Request):
    """Receive Razorpay invoice events."""
    body = await request.body()
    # TODO: process Razorpay invoice
    return {"received": True}


@router.post("/stripe")
async def stripe_webhook(request: Request):
    """Receive Stripe webhook events (subscription updates)."""
    body = await request.body()
    # TODO: verify signature and dispatch
    return {"received": True}