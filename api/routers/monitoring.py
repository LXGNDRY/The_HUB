"""
Monitoring router — metrics, quota usage, idle instance detection.
"""

import os
from fastapi import APIRouter, HTTPException
from auth.credentials import get_credentials
from config import QUOTA_ALERT_PERCENT, IDLE_CPU_THRESHOLD

router = APIRouter()
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")


def _monitoring():
    from modules.monitoring import MonitoringModule
    return MonitoringModule(PROJECT_ID, get_credentials())


@router.get("/quotas")
def quota_status():
    """Return all quotas above QUOTA_ALERT_PERCENT% utilization."""
    try:
        return _monitoring().get_quotas_above_threshold(threshold_percent=QUOTA_ALERT_PERCENT)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/idle-vms")
def idle_vms():
    """Return list of VMs with CPU below IDLE_CPU_THRESHOLD% in the last hour."""
    try:
        return [
            {"name": name, "zone": zone}
            for name, zone in _monitoring().get_low_cpu_instances(
                threshold_percent=IDLE_CPU_THRESHOLD, lookback_minutes=60
            )
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
