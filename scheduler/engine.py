"""
BotScheduler — APScheduler-based automation engine.
All jobs registered here with their triggers.
Runs as a background thread alongside the FastAPI server.

NOTE: Compute-dependent jobs (VM health, idle shutdown, snapshot cleanup)
are registered on schedule regardless — the jobs themselves detect
Compute Engine API availability and skip gracefully if unavailable.
No scheduler changes are needed when Compute Engine API is later enabled.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore

from scheduler.jobs import (
    cost_alert_job,
    cleanup_snapshots_job,
    vm_health_check_job,
    idle_vm_shutdown_job,
    monthly_report_job,
    storage_audit_job,
    quota_check_job,
    indexing_submission_job,
    sheets_refresh_job,
    error_log_monitor_job,
    shopify_product_health_job,
    gmc_disapproval_check_job,
    gmc_shipping_drift_check_job,
    klaviyo_flow_health_job,
    alt_text_auto_patch_job,
    indexnow_new_products_job,
    gmc_title_rotation_job,
    blog_writer_job,
    compliance_patch_job,
    product_type_patch_job,
    product_weight_patch_job,
)

logger = logging.getLogger("gcp-bot.scheduler")

JOBSTORES  = {"default": MemoryJobStore()}
EXECUTORS  = {"default": ThreadPoolExecutor(max_workers=5)}
JOB_DEFAULTS = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 60}


class BotScheduler:
    """
    Central scheduler for all GCP bot automation jobs.
    Compute jobs register normally — each job self-checks API availability.
    """

    def __init__(self, timezone: str = "America/Chicago"):
        self.scheduler = BackgroundScheduler(
            jobstores=JOBSTORES,
            executors=EXECUTORS,
            job_defaults=JOB_DEFAULTS,
            timezone=timezone,
        )
        self._register_jobs()

    def _register_jobs(self):
        """Register all automation jobs."""

        # Daily 8:00 AM — Billing alert (always runs)
        self.scheduler.add_job(
            cost_alert_job,
            CronTrigger(hour=8, minute=0),
            id="daily_cost_check",
            name="Daily Billing Alert",
            replace_existing=True,
        )

        # Monday 9:00 AM — Snapshot cleanup (skips if no Compute API)
        self.scheduler.add_job(
            cleanup_snapshots_job,
            CronTrigger(day_of_week="mon", hour=9, minute=0),
            id="weekly_snapshot_cleanup",
            name="Cleanup Old Snapshots (30d+) — requires Compute API",
            replace_existing=True,
        )

        # Every 15 min — VM health pulse (skips if no Compute API)
        self.scheduler.add_job(
            vm_health_check_job,
            IntervalTrigger(minutes=15),
            id="vm_health_pulse",
            name="VM Health Check — requires Compute API",
            replace_existing=True,
        )

        # Midnight nightly — Idle VM shutdown (skips if no Compute API)
        self.scheduler.add_job(
            idle_vm_shutdown_job,
            CronTrigger(hour=0, minute=0),
            id="nightly_idle_shutdown",
            name="Shutdown Idle VMs — requires Compute API",
            replace_existing=True,
        )

        # 1st of month 7:00 AM — Monthly report (partial if no Compute API)
        self.scheduler.add_job(
            monthly_report_job,
            CronTrigger(day=1, hour=7, minute=0),
            id="monthly_report",
            name="Monthly GCP Usage Report",
            replace_existing=True,
        )

        # Sunday 6:00 AM — Storage audit (always runs)
        self.scheduler.add_job(
            storage_audit_job,
            CronTrigger(day_of_week="sun", hour=6, minute=0),
            id="weekly_storage_audit",
            name="Storage Bucket Audit",
            replace_existing=True,
        )

        # Every 6 hours — Quota check (always runs)
        self.scheduler.add_job(
            quota_check_job,
            IntervalTrigger(hours=6),
            id="quota_check",
            name="Quota Usage Check (80% alert)",
            replace_existing=True,
        )

        # Daily 6:00 AM — Submit sitemap URLs to Google Indexing API
        self.scheduler.add_job(
            indexing_submission_job,
            CronTrigger(hour=6, minute=0),
            id="daily_indexing_submission",
            name="Daily Sitemap Indexing Submission",
            replace_existing=True,
        )

        # Daily 7:00 AM — Refresh Google Sheets dashboard with live data
        self.scheduler.add_job(
            sheets_refresh_job,
            CronTrigger(hour=7, minute=0),
            id="daily_sheets_refresh",
            name="Daily Sheets Dashboard Refresh",
            replace_existing=True,
        )

        # Every 6 hours — Monitor Cloud Run error logs
        self.scheduler.add_job(
            error_log_monitor_job,
            IntervalTrigger(hours=6),
            id="error_log_monitor",
            name="Cloud Run Error Log Monitor",
            replace_existing=True,
        )

        # ── Shopify & E-commerce Jobs ────────────────────────────────────────

        # Daily 09:00 — Shopify product data quality audit
        self.scheduler.add_job(
            shopify_product_health_job,
            CronTrigger(hour=9, minute=0),
            id="shopify_product_health",
            name="Shopify Product Health Check (SKU/barcode/type)",
            replace_existing=True,
        )

        # Daily 06:15 — IndexNow ping for products published in last 24h
        self.scheduler.add_job(
            indexnow_new_products_job,
            CronTrigger(hour=6, minute=15),
            id="indexnow_new_products",
            name="IndexNow: Ping New Products",
            replace_existing=True,
        )

        # Daily 06:30 — Auto-fill missing image alt text
        self.scheduler.add_job(
            alt_text_auto_patch_job,
            CronTrigger(hour=6, minute=30),
            id="alt_text_auto_patch",
            name="Alt Text Auto-Patch (images)",
            replace_existing=True,
        )

        # ── GMC Jobs ─────────────────────────────────────────────────────────

        # Daily 10:00 — GMC disapproval + data quality alert
        self.scheduler.add_job(
            gmc_disapproval_check_job,
            CronTrigger(hour=10, minute=0),
            id="gmc_disapproval_check",
            name="GMC Disapproval & Data Quality Check",
            replace_existing=True,
        )

        # Wednesday 08:00 — GMC × Shopify shipping drift (alert only)
        self.scheduler.add_job(
            gmc_shipping_drift_check_job,
            CronTrigger(day_of_week="wed", hour=8, minute=0),
            id="gmc_shipping_drift_check",
            name="GMC × Shopify Shipping Drift Check",
            replace_existing=True,
        )

        # ── Klaviyo Jobs ──────────────────────────────────────────────────────

        # Tuesday 08:00 — Klaviyo flow health check
        self.scheduler.add_job(
            klaviyo_flow_health_job,
            CronTrigger(day_of_week="tue", hour=8, minute=0),
            id="klaviyo_flow_health",
            name="Klaviyo Flow Health Check",
            replace_existing=True,
        )

        # ── GMC Title Rotation ────────────────────────────────────────────────

        # Wednesday 10:00 — GMC title A/B rotation (after shipping drift check)
        self.scheduler.add_job(
            gmc_title_rotation_job,
            CronTrigger(day_of_week="wed", hour=10, minute=0),
            id="gmc_title_rotation",
            name="GMC Title Rotation (CTR-based A/B)",
            replace_existing=True,
        )

        # ── Blog Writer Jobs ──────────────────────────────────────────────────
        # 3 posts/day spread across the day for SEO freshness signals

        # 08:00 — Morning blog post
        self.scheduler.add_job(
            blog_writer_job,
            CronTrigger(hour=8, minute=0),
            id="blog_writer_morning",
            name="Blog Writer — Morning Post (08:00 CT)",
            replace_existing=True,
        )

        # 12:00 — Midday blog post
        self.scheduler.add_job(
            blog_writer_job,
            CronTrigger(hour=12, minute=0),
            id="blog_writer_midday",
            name="Blog Writer — Midday Post (12:00 CT)",
            replace_existing=True,
        )

        # 16:00 — Afternoon blog post
        self.scheduler.add_job(
            blog_writer_job,
            CronTrigger(hour=16, minute=0),
            id="blog_writer_afternoon",
            name="Blog Writer — Afternoon Post (16:00 CT)",
            replace_existing=True,
        )

        # ── Compliance Jobs ───────────────────────────────────────────────────

        # Daily 02:00 — Fill missing COO + HS code on all variants (idempotent)
        self.scheduler.add_job(
            compliance_patch_job,
            CronTrigger(hour=2, minute=0),
            id="nightly_compliance_patch",
            name="Nightly COO + HS Code Compliance Patch",
            replace_existing=True,
        )

        # Daily 02:30 — Standardize product_type to Google Shopping taxonomy (idempotent)
        self.scheduler.add_job(
            product_type_patch_job,
            CronTrigger(hour=2, minute=30),
            id="nightly_product_type_patch",
            name="Nightly Product Type Taxonomy Patch",
            replace_existing=True,
        )

        # Daily 02:45 — Fill missing variant weights from taxonomy defaults (idempotent)
        self.scheduler.add_job(
            product_weight_patch_job,
            CronTrigger(hour=2, minute=45),
            id="nightly_product_weight_patch",
            name="Nightly Product Weight Patch",
            replace_existing=True,
        )

        logger.info("Registered %d scheduler jobs.", len(self.scheduler.get_jobs()))

    def start(self):
        self.scheduler.start()
        logger.info("BotScheduler started.")

    def stop(self):
        self.scheduler.shutdown(wait=False)
        logger.info("BotScheduler stopped.")

    def get_jobs(self) -> list[dict]:
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else "paused",
                "trigger": str(job.trigger),
                "status": "paused" if job.next_run_time is None else "active",
            }
            for job in self.scheduler.get_jobs()
        ]

    def pause_job(self, job_id: str):
        self.scheduler.pause_job(job_id)
        logger.info("Paused job: %s", job_id)

    def resume_job(self, job_id: str):
        self.scheduler.resume_job(job_id)
        logger.info("Resumed job: %s", job_id)

    def run_now(self, job_id: str):
        job = self.scheduler.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        job.func()
        logger.info("Manually triggered job: %s", job_id)
