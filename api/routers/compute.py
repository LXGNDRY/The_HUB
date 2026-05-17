"""
Compute Engine router — VM lifecycle management.
Endpoints: list, start, stop, delete instances.
"""

import os
from fastapi import APIRouter, HTTPException
from auth.credentials import get_credentials
from config import safe_execute

router = APIRouter()
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")


def _compute():
    from modules.compute import ComputeModule
    return ComputeModule(PROJECT_ID, get_credentials())


@router.get("/instances/{zone}")
def list_instances(zone: str):
    """List all VM instances in the given zone."""
    try:
        vms = _compute().list_instances(zone)
        return [{"name": vm.name, "status": vm.status, "zone": zone} for vm in vms]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/instances/{zone}/{name}/start")
def start_instance(zone: str, name: str):
    """Start a stopped VM instance."""
    try:
        safe_execute(f"start_instance:{name}@{zone}", _compute().start_instance, zone, name)
        return {"message": f"Started {name}", "zone": zone}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/instances/{zone}/{name}/stop")
def stop_instance(zone: str, name: str):
    """Stop a running VM instance."""
    try:
        safe_execute(f"stop_instance:{name}@{zone}", _compute().stop_instance, zone, name)
        return {"message": f"Stopped {name}", "zone": zone}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/instances/{zone}/{name}")
def delete_instance(zone: str, name: str):
    """Permanently delete a VM instance."""
    try:
        safe_execute(f"delete_instance:{name}@{zone}", _compute().delete_instance, zone, name)
        return {"message": f"Deleted {name}", "zone": zone}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
