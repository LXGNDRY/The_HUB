"""
The HUB — FastAPI Application Entry Point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info(f"{settings.APP_NAME} starting...")
    # ── Startup: init DB, stripe, scheduler ──
    yield
    # ── Shutdown ──
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ──
@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": "0.1.0"}


# ── Routers (lazy import to avoid circular deps) ──
def _register_routers():
    from app.routers import auth, shopify, billing, webhooks, tenants
    app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
    app.include_router(tenants.router, prefix="/api/tenants", tags=["Tenants"])
    app.include_router(shopify.router, prefix="/api/shopify", tags=["Shopify"])
    app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
    app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])


_register_routers()