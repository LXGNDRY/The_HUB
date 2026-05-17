"""
Scheduler — Automated Daily Jobs
=================================
Runs all agents on schedule using the `schedule` library.

Usage:
    python scheduler/jobs.py

Keep this running on a GCE VM, Cloud Run Job, or local machine.
For production: deploy as a Cloud Run Job with a Cloud Scheduler trigger.
"""

import os
import schedule
import time
from dotenv import load_dotenv

load_dotenv()

BQ_DATASET = os.getenv("BQ_BILLING_DATASET", "")
BQ_TABLE   = os.getenv("BQ_BILLING_TABLE",   "")
VM_ZONE    = os.getenv("DEFAULT_VM_ZONE",    "us-central1-a")


def job_billing_check():
    print("\n[scheduler] Running billing daily check...")
    from agents.billing_agent import BillingAgent
    BillingAgent().run_daily_check(
        bq_dataset=BQ_DATASET or None,
        bq_table=BQ_TABLE or None,
    )


def job_cleanup_snapshots():
    print("\n[scheduler] Cleaning up old snapshots...")
    from agents.compute_agent import ComputeAgent
    ComputeAgent().delete_snapshots_older_than(days=30)


def job_auto_stop_idle():
    print("\n[scheduler] Checking for idle VMs...")
    from agents.compute_agent import ComputeAgent
    ComputeAgent().auto_stop_idle(VM_ZONE, cpu_threshold=5.0)


# ── Schedule ────────────────────────────────────────────────
schedule.every().day.at("08:00").do(job_billing_check)
schedule.every().monday.at("09:00").do(job_cleanup_snapshots)
schedule.every().day.at("23:00").do(job_auto_stop_idle)

if __name__ == "__main__":
    print("[scheduler] GCP Bot scheduler started")
    print(f"  Billing check:      daily @ 08:00")
    print(f"  Snapshot cleanup:   Mondays @ 09:00")
    print(f"  Idle VM auto-stop:  daily @ 23:00")
    print()
    while True:
        schedule.run_pending()
        time.sleep(60)
