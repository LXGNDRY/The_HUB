"""
Global configuration and safety utilities for the GCP Bot.

DRY_RUN mode: set DRY_RUN=true in .env to log all destructive
actions without executing them. Essential for dev/staging.
"""

import os
import logging
import time
from functools import wraps

logger = logging.getLogger("gcp-bot.config")

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

DRY_RUN: bool = os.getenv("DRY_RUN", "false").lower() == "true"
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
GCP_ZONES: list[str] = os.getenv("GCP_ZONES", "us-central1-a,us-central1-b").split(",")
BUDGET_THRESHOLD: float = float(os.getenv("BUDGET_THRESHOLD", "100.0"))
IDLE_CPU_THRESHOLD: float = float(os.getenv("IDLE_CPU_THRESHOLD", "2.0"))
SNAPSHOT_MAX_AGE_DAYS: int = int(os.getenv("SNAPSHOT_MAX_AGE_DAYS", "30"))
QUOTA_ALERT_PERCENT: float = float(os.getenv("QUOTA_ALERT_PERCENT", "80.0"))
STORAGE_INACTIVE_DAYS: int = int(os.getenv("STORAGE_INACTIVE_DAYS", "90"))

# E-commerce automation
GMC_MERCHANT_ID: str = os.getenv("GMC_MERCHANT_ID", "")
INDEXNOW_API_KEY: str = os.getenv("INDEXNOW_API_KEY", "")
SITE_DOMAIN: str = os.getenv("SITE_DOMAIN", "legendary-branding.com")

if DRY_RUN:
    logger.warning("=== DRY RUN MODE ACTIVE — no destructive actions will execute ===")


# ---------------------------------------------------------------------------
# safe_execute — DRY_RUN gate for all destructive operations
# ---------------------------------------------------------------------------

def safe_execute(action_name: str, func, *args, **kwargs):
    """
    Execute a function only if DRY_RUN is False.
    In DRY_RUN mode, logs what would have been done and returns None.

    Usage:
        safe_execute("stop_instance:my-vm", compute.stop_instance, zone, vm_name)
    """
    if DRY_RUN:
        logger.info("[DRY RUN] Would execute: %s | args=%s kwargs=%s", action_name, args, kwargs)
        return None
    return func(*args, **kwargs)


# ---------------------------------------------------------------------------
# retry_with_backoff — exponential backoff for GCP API quota errors
# ---------------------------------------------------------------------------

def retry_with_backoff(max_attempts: int = 3, base_delay: float = 1.0):
    """
    Decorator: retry a function with exponential backoff on exception.
    Catches google.api_core ResourceExhausted and general transient errors.

    Usage:
        @retry_with_backoff(max_attempts=3)
        def call_gcp_api(): ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    wait = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "[retry] %s failed (attempt %d/%d): %s — retrying in %.1fs",
                        func.__name__, attempt, max_attempts, exc, wait,
                    )
                    if attempt < max_attempts:
                        time.sleep(wait)
            logger.error("[retry] %s exhausted %d attempts.", func.__name__, max_attempts)
            raise last_exc
        return wrapper
    return decorator
