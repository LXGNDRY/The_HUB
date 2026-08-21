"""The HUB multi-tenant API, quarantined until production controls pass."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.security import require_admin_api_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("%s starting (environment=%s, saas_enabled=%s)", settings.APP_NAME, settings.ENVIRONMENT, settings.SAAS_ENABLED)
    yield
    logger.info("%s shutting down", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Hub-Admin-Key", "X-Request-Id"],
)


@app.middleware("http")
async def quarantine_and_authenticate(request: Request, call_next):
    path = request.url.path
    if path in {"/health", "/ready"} or path.startswith("/api/webhooks/"):
        return await call_next(request)
    if not settings.SAAS_ENABLED:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "hub-backend is quarantined pending production readiness."},
        )
    try:
        await require_admin_api_key(request, settings.HUB_ADMIN_API_KEY)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": "0.2.0"}


@app.get("/ready", include_in_schema=False)
def readiness():
    if not settings.SAAS_ENABLED:
        raise HTTPException(status_code=503, detail="SaaS surface is intentionally disabled.")
    return {"status": "ready"}


def _register_routers() -> None:
    from app.routers import auth, billing, shopify, tenants, webhooks

    app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
    app.include_router(tenants.router, prefix="/api/tenants", tags=["Tenants"])
    app.include_router(shopify.router, prefix="/api/shopify", tags=["Shopify"])
    app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
    app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])


_register_routers()
