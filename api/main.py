"""
GCP Bot — FastAPI application entry point.
Mounts all routers and starts the APScheduler on app startup.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.middleware.auth import verify_api_key
from api.routers import compute, storage, billing, monitoring, seo, analytics, pagespeed
from api.routers import gemini, sheets, indexing, tag_manager, secrets, logs, higgsfield
from scheduler.engine import BotScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("gcp-bot.api")

# Global scheduler instance
bot_scheduler = BotScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start scheduler on boot; cleanly stop on shutdown."""
    bot_scheduler.start()
    logger.info("GCP Bot API ready.")
    yield
    bot_scheduler.stop()
    logger.info("GCP Bot API shutting down.")


app = FastAPI(
    title="GCP Control Bot",
    description="Autonomous GCP management API — compute, storage, billing, monitoring, scheduler.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — restrict in production to your dashboard origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------------
# Resource routers
# -------------------------------------------------------------------------
protected = {"dependencies": [Depends(verify_api_key)]}

app.include_router(compute.router,    prefix="/api/compute",    tags=["Compute"],    **protected)
app.include_router(storage.router,    prefix="/api/storage",    tags=["Storage"],    **protected)
app.include_router(billing.router,    prefix="/api/billing",    tags=["Billing"],    **protected)
app.include_router(monitoring.router, prefix="/api/monitoring", tags=["Monitoring"], **protected)
app.include_router(seo.router,        prefix="/api/seo",        tags=["SEO"],        **protected)
app.include_router(analytics.router,  prefix="/api/analytics",  tags=["Analytics"],  **protected)
app.include_router(pagespeed.router,  prefix="/api/pagespeed",  tags=["PageSpeed"],  **protected)
app.include_router(gemini.router,     prefix="/api/gemini",     tags=["Gemini AI"],  **protected)
app.include_router(sheets.router,     prefix="/api/sheets",     tags=["Sheets"],     **protected)
app.include_router(indexing.router,   prefix="/api/indexing",   tags=["Indexing"],   **protected)
app.include_router(tag_manager.router,prefix="/api/gtm",        tags=["Tag Manager"],**protected)
app.include_router(secrets.router,    prefix="/api/secrets",    tags=["Secrets"],    **protected)
app.include_router(logs.router,        prefix="/api/logs",        tags=["Logs"],        **protected)
app.include_router(higgsfield.router,  prefix="/api/higgsfield",  tags=["Higgsfield AI"], **protected)

# -------------------------------------------------------------------------
# Scheduler control routes
# -------------------------------------------------------------------------

@app.get("/api/scheduler/jobs", tags=["Scheduler"], **protected)
def list_jobs():
    """List all registered automation jobs and their next run times."""
    return bot_scheduler.get_jobs()


@app.post("/api/scheduler/jobs/{job_id}/pause", tags=["Scheduler"], **protected)
def pause_job(job_id: str):
    """Pause a scheduled job by ID."""
    try:
        bot_scheduler.pause_job(job_id)
        return {"status": "paused", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/scheduler/jobs/{job_id}/resume", tags=["Scheduler"], **protected)
def resume_job(job_id: str):
    """Resume a paused job by ID."""
    try:
        bot_scheduler.resume_job(job_id)
        return {"status": "resumed", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/scheduler/jobs/{job_id}/run", tags=["Scheduler"], **protected)
def trigger_job(job_id: str):
    """Manually trigger a job immediately, outside its schedule."""
    try:
        bot_scheduler.run_now(job_id)
        return {"status": "triggered", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


# -------------------------------------------------------------------------
# Health check (unauthenticated — for uptime monitoring)
# -------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health():
    """Simple health check endpoint."""
    return {"status": "ok", "scheduler_jobs": len(bot_scheduler.get_jobs())}
