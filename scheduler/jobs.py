"""
Job definitions for the GCP Bot scheduler.
Each function is a standalone, independently testable unit.
All destructive actions are wrapped in safe_execute() for dry-run support.

Compute Engine API is OPTIONAL — if unavailable, all compute-dependent
jobs log a clear warning and skip gracefully without crashing the scheduler.
"""

import os
import logging
from datetime import datetime, timezone

from config import safe_execute, DRY_RUN
from notifications import send_alert
from auth.credentials import get_credentials

logger = logging.getLogger("gcp-bot.jobs")

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
BUDGET_THRESHOLD = float(os.getenv("BUDGET_THRESHOLD", "100.0"))
IDLE_CPU_THRESHOLD = float(os.getenv("IDLE_CPU_THRESHOLD", "2.0"))
SNAPSHOT_MAX_AGE_DAYS = int(os.getenv("SNAPSHOT_MAX_AGE_DAYS", "30"))
QUOTA_ALERT_PERCENT = float(os.getenv("QUOTA_ALERT_PERCENT", "80.0"))
STORAGE_INACTIVE_DAYS = int(os.getenv("STORAGE_INACTIVE_DAYS", "90"))
GCP_ZONES = os.getenv("GCP_ZONES", "us-central1-a,us-central1-b").split(",")


# ---------------------------------------------------------------------------
# Compute availability check — run once at import time
# ---------------------------------------------------------------------------

def _compute_available() -> bool:
    """
    Returns True if google-cloud-compute is installed AND
    the Compute Engine API is reachable for this project.
    Caches result to avoid redundant API calls.
    """
    if not hasattr(_compute_available, "_cached"):
        try:
            import google.cloud.compute_v1  # noqa: F401
            _compute_available._cached = True
            logger.info("[compute_check] Compute Engine API available.")
        except (ImportError, Exception) as e:
            _compute_available._cached = False
            logger.warning(
                "[compute_check] Compute Engine API unavailable — "
                "VM jobs will be skipped until enabled. Reason: %s", e
            )
    return _compute_available._cached


def _compute_skip_notice(job_name: str):
    """Log a clean skip message for compute-dependent jobs."""
    logger.warning(
        "[%s] Skipped — Compute Engine API not enabled. "
        "Enable it at: console.cloud.google.com/apis/library/compute.googleapis.com",
        job_name,
    )


# ---------------------------------------------------------------------------
# JOB 1 — Daily Billing Cost Alert  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def cost_alert_job():
    """
    Fetches monthly and daily GCP spend.
    Sends an alert if monthly spend exceeds BUDGET_THRESHOLD.
    """
    logger.info("[cost_alert_job] Running...")
    try:
        from modules.billing import BillingModule
        billing = BillingModule(get_credentials())
        monthly_data = billing.get_monthly_spend()
        daily_data = billing.get_today_spend()
        top_services = billing.get_top_services(limit=3)

        # get_monthly_spend returns a dict — extract a note string for the report
        billing_account = monthly_data.get("billing_account", "unknown")
        billing_enabled = monthly_data.get("billing_enabled", False)
        monthly_note = monthly_data.get("note", "")
        daily_note = daily_data.get("note", "")
        top_svc_names = [s.get("service", str(s)) for s in top_services]

        summary = (
            f"📊 *GCP Daily Cost Report* — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"Billing Account : {billing_account}\n"
            f"Billing Enabled : {billing_enabled}\n"
            f"Spend Note      : {monthly_note}\n"
            f"Daily Note      : {daily_note}\n"
            f"Top Services    : {', '.join(top_svc_names)}"
        )

        send_alert(summary)
        logger.info("[cost_alert_job] Completed. Billing enabled: %s", billing_enabled)

    except Exception as e:
        logger.error("[cost_alert_job] Failed: %s", e)
        send_alert(f"❌ cost_alert_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 2 — Weekly Snapshot Cleanup  [COMPUTE REQUIRED — GRACEFUL SKIP]
# ---------------------------------------------------------------------------

def cleanup_snapshots_job():
    """
    Deletes GCP disk snapshots older than SNAPSHOT_MAX_AGE_DAYS.
    Skips gracefully if Compute Engine API is not enabled.
    """
    logger.info("[cleanup_snapshots_job] Running...")

    if not _compute_available():
        _compute_skip_notice("cleanup_snapshots_job")
        return

    try:
        from modules.compute import ComputeModule
        compute = ComputeModule(PROJECT_ID, get_credentials())
        old_snapshots = compute.get_snapshots_older_than(days=SNAPSHOT_MAX_AGE_DAYS)

        deleted_count = 0
        for snapshot in old_snapshots:
            result = safe_execute(
                f"delete_snapshot:{snapshot.name}",
                compute.delete_snapshot,
                snapshot.name,
            )
            if result is not None or not DRY_RUN:
                deleted_count += 1

        msg = f"🧹 Snapshot cleanup: {deleted_count} snapshot(s) removed (>{SNAPSHOT_MAX_AGE_DAYS}d old)"
        if DRY_RUN:
            msg = f"[DRY RUN] {msg}"
        send_alert(msg)
        logger.info("[cleanup_snapshots_job] Completed. Deleted: %d", deleted_count)

    except Exception as e:
        logger.error("[cleanup_snapshots_job] Failed: %s", e)
        send_alert(f"❌ cleanup_snapshots_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 3 — VM Health Check  [COMPUTE REQUIRED — GRACEFUL SKIP]
# ---------------------------------------------------------------------------

def vm_health_check_job():
    """
    Scans all configured zones for VMs in unexpected states.
    Skips gracefully if Compute Engine API is not enabled.
    """
    logger.info("[vm_health_check_job] Running across zones: %s", GCP_ZONES)

    if not _compute_available():
        _compute_skip_notice("vm_health_check_job")
        return

    try:
        from modules.compute import ComputeModule
        compute = ComputeModule(PROJECT_ID, get_credentials())

        issues = []
        healthy_count = 0

        for zone in GCP_ZONES:
            for vm in compute.list_instances(zone):
                if vm.status not in ("RUNNING", "TERMINATED", "STOPPED"):
                    issues.append(f"⚠️ {vm.name} [{zone}] → {vm.status}")
                else:
                    healthy_count += 1

        if issues:
            send_alert("🔴 *VM Health Issues Detected*\n" + "\n".join(issues))
            logger.warning("[vm_health_check_job] %d issue(s) found.", len(issues))
        else:
            logger.info("[vm_health_check_job] All %d VMs healthy.", healthy_count)

    except Exception as e:
        logger.error("[vm_health_check_job] Failed: %s", e)
        send_alert(f"❌ vm_health_check_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 4 — Nightly Idle VM Auto-Shutdown  [COMPUTE REQUIRED — GRACEFUL SKIP]
# ---------------------------------------------------------------------------

def idle_vm_shutdown_job():
    """
    Stops VMs with average CPU < IDLE_CPU_THRESHOLD% over the last 60 minutes.
    Skips gracefully if Compute Engine API is not enabled.
    """
    logger.info("[idle_vm_shutdown_job] Running...")

    if not _compute_available():
        _compute_skip_notice("idle_vm_shutdown_job")
        return

    try:
        from modules.compute import ComputeModule
        from modules.monitoring import MonitoringModule
        compute = ComputeModule(PROJECT_ID, get_credentials())
        monitoring = MonitoringModule(PROJECT_ID, get_credentials())

        idle_vms = monitoring.get_low_cpu_instances(
            threshold_percent=IDLE_CPU_THRESHOLD,
            lookback_minutes=60,
            exclude_label="no-autostop",
        )

        stopped = []
        for vm_name, zone in idle_vms:
            safe_execute(
                f"stop_instance:{vm_name}@{zone}",
                compute.stop_instance,
                zone,
                vm_name,
            )
            stopped.append(f"{vm_name} ({zone})")

        if stopped:
            msg = f"💤 *Idle VM Shutdown* — {len(stopped)} stopped:\n" + "\n".join(stopped)
            if DRY_RUN:
                msg = f"[DRY RUN] {msg}"
            send_alert(msg)
        logger.info("[idle_vm_shutdown_job] Stopped: %d VMs", len(stopped))

    except Exception as e:
        logger.error("[idle_vm_shutdown_job] Failed: %s", e)
        send_alert(f"❌ idle_vm_shutdown_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 5 — Monthly GCP Usage Report  [COMPUTE OPTIONAL — PARTIAL IF MISSING]
# ---------------------------------------------------------------------------

def monthly_report_job():
    """
    Generates a full monthly GCP usage summary.
    VM count is reported as 'N/A' if Compute Engine API is unavailable.
    """
    logger.info("[monthly_report_job] Running...")
    try:
        from modules.billing import BillingModule
        from modules.storage import StorageModule
        billing = BillingModule(get_credentials())
        storage = StorageModule(get_credentials())

        monthly_data = billing.get_monthly_spend()
        spend_by_service = billing.get_spend_by_service()
        buckets = storage.list_buckets()
        total_buckets = len(list(buckets))

        billing_account = monthly_data.get("billing_account", "unknown")
        billing_enabled = monthly_data.get("billing_enabled", False)
        monthly_note = monthly_data.get("note", "No spend data available.")

        # VM count: include if compute available, show N/A otherwise
        if _compute_available():
            from modules.compute import ComputeModule
            compute = ComputeModule(PROJECT_ID, get_credentials())
            total_vms = sum(len(compute.list_instances(z)) for z in GCP_ZONES)
            vm_line = f"Active VMs    : {total_vms}"
        else:
            vm_line = "Active VMs    : N/A (Compute Engine API not enabled)"

        service_lines = "\n".join(
            [f"  • {svc}" for svc in spend_by_service]
        ) if spend_by_service else "  (Billing export to BigQuery required for per-service data)"

        report = (
            f"📅 *Monthly GCP Report — {datetime.now(timezone.utc).strftime('%B %Y')}*\n"
            f"Billing Account : {billing_account} (enabled={billing_enabled})\n"
            f"Spend Note      : {monthly_note}\n"
            f"{vm_line}\n"
            f"Storage Buckets : {total_buckets}\n\n"
            f"*Active Services:*\n{service_lines}"
        )
        send_alert(report)
        logger.info("[monthly_report_job] Completed. Billing enabled: %s", billing_enabled)

    except Exception as e:
        logger.error("[monthly_report_job] Failed: %s", e)
        send_alert(f"❌ monthly_report_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 6 — Weekly Storage Bucket Audit  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def storage_audit_job():
    """
    Flags GCP Storage buckets with no object access in STORAGE_INACTIVE_DAYS days.
    """
    logger.info("[storage_audit_job] Running...")
    try:
        from modules.storage import StorageModule
        storage = StorageModule(get_credentials())
        stale = storage.get_inactive_buckets(days=STORAGE_INACTIVE_DAYS)

        if stale:
            bucket_lines = "\n".join([f"  • {b}" for b in stale])
            send_alert(
                f"🗂️ *Storage Audit* — {len(stale)} inactive bucket(s) (>{STORAGE_INACTIVE_DAYS}d):\n"
                + bucket_lines
            )
        else:
            logger.info("[storage_audit_job] No inactive buckets found.")

        logger.info("[storage_audit_job] Completed. Stale: %d", len(stale))

    except Exception as e:
        logger.error("[storage_audit_job] Failed: %s", e)
        send_alert(f"❌ storage_audit_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 7 — Quota Usage Check  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def quota_check_job():
    """
    Checks all GCP service quotas.
    Alerts if any quota is above QUOTA_ALERT_PERCENT% utilization.
    """
    logger.info("[quota_check_job] Running...")
    try:
        from modules.monitoring import MonitoringModule
        monitoring = MonitoringModule(PROJECT_ID, get_credentials())
        over_quota = monitoring.get_quotas_above_threshold(
            threshold_percent=QUOTA_ALERT_PERCENT
        )

        if over_quota:
            lines = "\n".join(
                [f"  ⚠️ {q['metric']}: {q['percent']:.1f}%" for q in over_quota]
            )
            send_alert(
                f"📈 *Quota Alert* — {len(over_quota)} quota(s) above {QUOTA_ALERT_PERCENT}%:\n"
                + lines
            )
            logger.warning("[quota_check_job] %d quotas near limit.", len(over_quota))
        else:
            logger.info("[quota_check_job] All quotas within safe range.")

    except Exception as e:
        logger.error("[quota_check_job] Failed: %s", e)
        send_alert(f"❌ quota_check_job failed: {e}")
