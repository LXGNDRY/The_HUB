"""
api/routers/logs.py — Cloud Logging API endpoints

Routes:
  GET  /api/logs/recent                   — Get recent Cloud Run logs
  GET  /api/logs/errors                   — Get error logs only
  GET  /api/logs/requests                 — Get HTTP request logs
  GET  /api/logs/error-summary            — Error count by severity + top errors
  GET  /api/logs/endpoint-stats           — Per-endpoint request/error/latency stats
  POST /api/logs/search                   — Search logs by keyword
  POST /api/logs/write                    — Write a log entry (audit trail)
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.credentials import get_credentials

logger = logging.getLogger("gcp-bot.api.logs")
router = APIRouter()


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class SearchLogsRequest(BaseModel):
    keyword: str
    hours_back: int = 24
    limit: int = 50


class WriteLogRequest(BaseModel):
    message: str
    severity: str = "INFO"
    labels: Optional[dict] = None


# ------------------------------------------------------------------
# Module factory
# ------------------------------------------------------------------

def _get_module():
    try:
        from modules.cloud_logging import CloudLoggingModule
        return CloudLoggingModule(get_credentials())
    except Exception as e:
        logger.error("[logs router] Module init failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/recent")
def get_recent_logs(hours_back: int = 24, limit: int = 100, severity_min: str = "DEFAULT"):
    """
    Get recent Cloud Run logs.

    Query params:
      hours_back   — How many hours back to look (default 24)
      limit        — Max entries to return (default 100)
      severity_min — Minimum severity: DEBUG, INFO, WARNING, ERROR, CRITICAL
    """
    mod = _get_module()
    try:
        logs = mod.get_recent_logs(hours_back=hours_back, limit=limit, severity_min=severity_min)
        return {"logs": logs, "count": len(logs), "hours_back": hours_back}
    except Exception as e:
        logger.error("[logs] get_recent_logs failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/errors")
def get_error_logs(hours_back: int = 24, limit: int = 50):
    """Get ERROR-level and above logs from Cloud Run."""
    mod = _get_module()
    try:
        logs = mod.get_error_logs(hours_back=hours_back, limit=limit)
        return {"logs": logs, "count": len(logs), "hours_back": hours_back}
    except Exception as e:
        logger.error("[logs] get_error_logs failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/requests")
def get_request_logs(hours_back: int = 24, limit: int = 100):
    """Get HTTP request/access logs from Cloud Run."""
    mod = _get_module()
    try:
        logs = mod.get_request_logs(hours_back=hours_back, limit=limit)
        return {"logs": logs, "count": len(logs), "hours_back": hours_back}
    except Exception as e:
        logger.error("[logs] get_request_logs failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/error-summary")
def error_summary(hours_back: int = 24):
    """
    Get a summary of error counts by severity level.
    Includes top recurring error messages.
    """
    mod = _get_module()
    try:
        return mod.get_error_summary(hours_back=hours_back)
    except Exception as e:
        logger.error("[logs] error_summary failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/endpoint-stats")
def endpoint_stats(hours_back: int = 24):
    """
    Get per-endpoint stats: request count, error count, error rate, avg latency.
    """
    mod = _get_module()
    try:
        stats = mod.get_endpoint_stats(hours_back=hours_back)
        return {"endpoints": stats, "count": len(stats), "hours_back": hours_back}
    except Exception as e:
        logger.error("[logs] endpoint_stats failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
def search_logs(body: SearchLogsRequest):
    """Search Cloud Run logs for a specific keyword or pattern."""
    mod = _get_module()
    try:
        logs = mod.search_logs(body.keyword, hours_back=body.hours_back, limit=body.limit)
        return {"keyword": body.keyword, "logs": logs, "count": len(logs)}
    except Exception as e:
        logger.error("[logs] search_logs failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/write")
def write_log(body: WriteLogRequest):
    """Write a custom log entry to Cloud Logging (for audit trail)."""
    mod = _get_module()
    try:
        mod.write_log(body.message, severity=body.severity, labels=body.labels)
        return {"status": "logged", "message": body.message, "severity": body.severity}
    except Exception as e:
        logger.error("[logs] write_log failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
