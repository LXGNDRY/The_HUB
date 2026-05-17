"""
BotScheduler — APScheduler-based automation engine.
All jobs are registered here with their triggers.
The scheduler runs as a background thread alongside the FastAPI server.
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
)

logger = logging.getLogger("gcp-bot.scheduler")

# APScheduler configuration
JOBSTORES = {"default": MemoryJobStore()}
EXECUTORS = {"default": ThreadPoolExecutor(max_workers=5)}
JOB_DEFAULTS = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 60}


class BotScheduler:
    """
    Central scheduler for all GCP bot automation jobs.
    Wraps APScheduler with register, control, and introspection methods.
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
        """Register all automation jobs with their schedules."""

        # --- Daily: Billing cost check at 8:00 AM CDT ---
        self.scheduler.add_job(
            cost_alert_job,
            CronTrigger(hour=8, minute=0),
            id="daily_cost_check",
            name="Daily Billing Alert",
            replace_existing=True,
        )

        # --- Weekly: Snapshot cleanup every Monday at 9:00 AM ---
        self.scheduler.add_job(
            cleanup_snapshots_job,
            CronTrigger(day_of_week="mon", hour=9, minute=0),
            id="weekly_snapshot_cleanup",
            name="Cleanup Old Snapshots (30d+)",
            replace_existing=True,
        )

        # --- Every 15 min: VM health pulse ---
        self.scheduler.add_job(
            vm_health_check_job,
            IntervalTrigger(minutes=15),
            id="vm_health_pulse",
            name="VM Health Check",
            replace_existing=True,
        )

        # --- Nightly: Idle VM auto-shutdown at midnight ---
        self.scheduler.add_job(
            idle_vm_shutdown_job,
            CronTrigger(hour=0, minute=0),
            id="nightly_idle_shutdown",
            name="Shutdown Idle VMs",
            replace_existing=True,
        )

        # --- Monthly: Full GCP usage report on 1st of month at 7:00 AM ---
        self.scheduler.add_job(
            monthly_report_job,
            CronTrigger(day=1, hour=7, minute=0),
            id="monthly_report",
            name="Monthly GCP Usage Report",
            replace_existing=True,
        )

        # --- Weekly: Storage bucket audit every Sunday at 6:00 AM ---
        self.scheduler.add_job(
            storage_audit_job,
            CronTrigger(day_of_week="sun", hour=6, minute=0),
            id="weekly_storage_audit",
            name="Storage Bucket Audit",
            replace_existing=True,
        )

        # --- Every 6 hours: Quota usage check ---
        self.scheduler.add_job(
            quota_check_job,
            IntervalTrigger(hours=6),
            id="quota_check",
            name="Quota Usage Check (80% alert)",
            replace_existing=True,
        )

        logger.info("Registered %d scheduler jobs.", len(self.scheduler.get_jobs()))

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self):
        self.scheduler.start()
        logger.info("BotScheduler started.")

    def stop(self):
        self.scheduler.shutdown(wait=False)
        logger.info("BotScheduler stopped.")

    # -------------------------------------------------------------------------
    # Introspection & Control (exposed via FastAPI /api/scheduler routes)
    # -------------------------------------------------------------------------

    def get_jobs(self) -> list[dict]:
        """Return serializable list of all registered jobs."""
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
        """Immediately execute a job outside its schedule."""
        job = self.scheduler.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        job.func()
        logger.info("Manually triggered job: %s", job_id)
