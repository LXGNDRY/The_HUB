"""
Compute Agent
=============
Manages Google Compute Engine VM instances:
  - List instances across zones
  - Start / stop / restart instances
  - Delete instances
  - Create instances from a config dict
  - List and delete snapshots
  - Auto-stop idle instances based on CPU threshold
  - Dry-run mode for all destructive operations

Required IAM roles on service account:
  roles/compute.instanceAdmin.v1
  roles/compute.viewer
"""

import os
import time
from typing import Optional

from google.cloud import compute_v1
from google.oauth2 import service_account
from google.api_core.exceptions import GoogleAPICallError
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID       = os.getenv("GCP_PROJECT_ID")
CREDENTIALS_PATH = os.getenv("GCP_CREDENTIALS_PATH", "auth/service_account.json")
DEPLOY_SCOPES   = ["https://www.googleapis.com/auth/cloud-platform"]


# ─── Auth ──────────────────────────────────────────────────────────
def get_credentials() -> service_account.Credentials:
    return service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH, scopes=DEPLOY_SCOPES
    )


# ─── Retry wrapper ─────────────────────────────────────────────────
def with_retry(fn, max_attempts: int = 3):
    """Exponential backoff on quota / transient errors."""
    for attempt in range(max_attempts):
        try:
            return fn()
        except GoogleAPICallError as e:
            if attempt == max_attempts - 1:
                raise
            wait = 2 ** attempt
            print(f"  [retry] {e.message} — retrying in {wait}s")
            time.sleep(wait)


# ─── Core Agent ────────────────────────────────────────────────────
class ComputeAgent:
    """
    Full lifecycle management for GCE VM instances.

    Usage:
        agent = ComputeAgent()
        agent.list_instances("us-central1-a")
        agent.stop_instance("us-central1-a", "my-vm")
        agent.start_instance("us-central1-a", "my-vm")
    """

    def __init__(self, dry_run: bool = False):
        creds = get_credentials()
        self.project_id      = PROJECT_ID
        self.dry_run         = dry_run
        self.instances_client = compute_v1.InstancesClient(credentials=creds)
        self.snapshots_client = compute_v1.SnapshotsClient(credentials=creds)
        self.disks_client     = compute_v1.DisksClient(credentials=creds)
        self.zones_client     = compute_v1.ZonesClient(credentials=creds)
        if dry_run:
            print("[compute] DRY RUN MODE — no changes will be made")

    # ── List ───────────────────────────────────────────────────────
    def list_instances(self, zone: str) -> list:
        """
        List all VM instances in a zone.

        Returns:
            List of compute_v1.Instance objects.
        """
        instances = list(with_retry(lambda: self.instances_client.list(
            project=self.project_id, zone=zone
        )))
        for vm in instances:
            print(f"  {vm.name:<30} status={vm.status:<12} machine={vm.machine_type.split('/')[-1]}")
        return instances

    def list_all_instances(self) -> dict:
        """
        List instances across ALL zones in the project.

        Returns:
            Dict of {zone: [instances]}.
        """
        zones = [z.name for z in with_retry(lambda: self.zones_client.list(project=self.project_id))]
        result = {}
        for zone in zones:
            vms = list(self.instances_client.list(project=self.project_id, zone=zone))
            if vms:
                result[zone] = vms
                for vm in vms:
                    print(f"  [{zone}] {vm.name:<30} {vm.status}")
        return result

    # ── Start ──────────────────────────────────────────────────────
    def start_instance(self, zone: str, name: str) -> None:
        """Start a stopped VM instance."""
        print(f"[compute] Starting {name} in {zone}...")
        if self.dry_run:
            print("  [dry-run] skipped")
            return
        op = with_retry(lambda: self.instances_client.start(
            project=self.project_id, zone=zone, instance=name
        ))
        self._wait_for_operation(op, zone)
        print(f"  ✅ {name} started")

    # ── Stop ───────────────────────────────────────────────────────
    def stop_instance(self, zone: str, name: str) -> None:
        """Stop a running VM instance."""
        print(f"[compute] Stopping {name} in {zone}...")
        if self.dry_run:
            print("  [dry-run] skipped")
            return
        op = with_retry(lambda: self.instances_client.stop(
            project=self.project_id, zone=zone, instance=name
        ))
        self._wait_for_operation(op, zone)
        print(f"  ✅ {name} stopped")

    # ── Restart ────────────────────────────────────────────────────
    def restart_instance(self, zone: str, name: str) -> None:
        """Reset (hard restart) a VM instance."""
        print(f"[compute] Restarting {name} in {zone}...")
        if self.dry_run:
            print("  [dry-run] skipped")
            return
        op = with_retry(lambda: self.instances_client.reset(
            project=self.project_id, zone=zone, instance=name
        ))
        self._wait_for_operation(op, zone)
        print(f"  ✅ {name} restarted")

    # ── Delete ─────────────────────────────────────────────────────
    def delete_instance(self, zone: str, name: str) -> None:
        """Permanently delete a VM instance. Irreversible."""
        print(f"[compute] Deleting {name} in {zone}...")
        if self.dry_run:
            print("  [dry-run] skipped")
            return
        op = with_retry(lambda: self.instances_client.delete(
            project=self.project_id, zone=zone, instance=name
        ))
        self._wait_for_operation(op, zone)
        print(f"  ✅ {name} deleted")

    # ── Create ─────────────────────────────────────────────────────
    def create_instance(
        self,
        zone: str,
        name: str,
        machine_type: str = "e2-micro",
        image_project: str = "debian-cloud",
        image_family: str = "debian-12",
        disk_size_gb: int = 20,
        tags: Optional[list] = None,
    ) -> None:
        """
        Create a new VM instance with a standard boot disk.

        Args:
            zone:          GCP zone, e.g. "us-central1-a"
            name:          Instance name (lowercase, hyphens allowed)
            machine_type:  e.g. "e2-micro", "n2-standard-2"
            image_project: Boot disk image project
            image_family:  Boot disk image family
            disk_size_gb:  Boot disk size in GB
            tags:          Network tags list
        """
        print(f"[compute] Creating {name} ({machine_type}) in {zone}...")
        if self.dry_run:
            print("  [dry-run] skipped")
            return

        machine_type_url = f"zones/{zone}/machineTypes/{machine_type}"
        image_url = (
            f"projects/{image_project}/global/images/family/{image_family}"
        )

        instance = compute_v1.Instance(
            name=name,
            machine_type=machine_type_url,
            disks=[
                compute_v1.AttachedDisk(
                    boot=True,
                    auto_delete=True,
                    initialize_params=compute_v1.AttachedDiskInitializeParams(
                        source_image=image_url,
                        disk_size_gb=disk_size_gb,
                    ),
                )
            ],
            network_interfaces=[
                compute_v1.NetworkInterface(
                    name="global/networks/default",
                    access_configs=[
                        compute_v1.AccessConfig(
                            name="External NAT",
                            type_="ONE_TO_ONE_NAT",
                        )
                    ],
                )
            ],
            tags=compute_v1.Tags(items=tags or []),
        )

        op = with_retry(lambda: self.instances_client.insert(
            project=self.project_id, zone=zone, instance_resource=instance
        ))
        self._wait_for_operation(op, zone)
        print(f"  ✅ {name} created")

    # ── Snapshots ──────────────────────────────────────────────────
    def list_snapshots(self) -> list:
        """List all disk snapshots in the project."""
        snaps = list(with_retry(lambda: self.snapshots_client.list(project=self.project_id)))
        for s in snaps:
            created = getattr(s, 'creation_timestamp', 'unknown')
            print(f"  {s.name:<40} created={created}")
        return snaps

    def delete_snapshots_older_than(self, days: int = 30) -> int:
        """
        Delete snapshots older than N days.

        Returns:
            Number of snapshots deleted.
        """
        import datetime
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        snaps = list(self.snapshots_client.list(project=self.project_id))
        deleted = 0
        for s in snaps:
            ts_str = getattr(s, 'creation_timestamp', None)
            if not ts_str:
                continue
            # GCP returns RFC 3339 — strip timezone offset for naive parse
            ts = datetime.datetime.fromisoformat(ts_str[:19])
            if ts < cutoff:
                print(f"  [snapshot] Deleting {s.name} (created {ts_str[:10]})")
                if not self.dry_run:
                    with_retry(lambda sn=s: self.snapshots_client.delete(
                        project=self.project_id, snapshot=sn.name
                    ))
                deleted += 1
        print(f"  ✅ Deleted {deleted} snapshots older than {days} days")
        return deleted

    # ── Auto-Stop Idle VMs ─────────────────────────────────────────
    def auto_stop_idle(self, zone: str, cpu_threshold: float = 5.0) -> list:
        """
        Stop RUNNING VMs whose average CPU utilization is below threshold.
        Uses Cloud Monitoring to fetch CPU metrics.

        Args:
            zone:          Zone to check.
            cpu_threshold: Stop VMs with avg CPU % below this value.

        Returns:
            List of instance names that were stopped.
        """
        from google.cloud import monitoring_v3
        import datetime

        creds    = get_credentials()
        m_client = monitoring_v3.MetricServiceClient(credentials=creds)
        project_name = f"projects/{self.project_id}"

        now   = datetime.datetime.utcnow()
        start = now - datetime.timedelta(hours=1)

        interval = monitoring_v3.TimeInterval(
            end_time={"seconds": int(now.timestamp())},
            start_time={"seconds": int(start.timestamp())},
        )

        results = m_client.list_time_series(
            request={
                "name": project_name,
                "filter": 'metric.type="compute.googleapis.com/instance/cpu/utilization"',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )

        stopped = []
        for ts in results:
            instance_name = ts.resource.labels.get("instance_id", "")
            instance_zone = ts.resource.labels.get("zone", "")
            if zone not in instance_zone:
                continue
            if not ts.points:
                continue
            avg_cpu = sum(p.value.double_value for p in ts.points) / len(ts.points) * 100
            print(f"  {instance_name}: avg CPU = {avg_cpu:.2f}%")
            if avg_cpu < cpu_threshold:
                print(f"  → below threshold ({cpu_threshold}%), stopping...")
                self.stop_instance(zone, instance_name)
                stopped.append(instance_name)

        return stopped

    # ── Operation Waiter ───────────────────────────────────────────
    def _wait_for_operation(self, operation, zone: str, timeout: int = 120) -> None:
        """Poll a zonal operation until it completes or times out."""
        zone_ops_client = compute_v1.ZoneOperationsClient(credentials=get_credentials())
        start = time.time()
        while True:
            op = zone_ops_client.get(
                project=self.project_id,
                zone=zone,
                operation=operation.name,
            )
            if op.status == compute_v1.Operation.Status.DONE:
                if op.error:
                    raise RuntimeError(f"Operation failed: {op.error}")
                return
            if time.time() - start > timeout:
                raise TimeoutError(f"Operation {operation.name} timed out after {timeout}s")
            time.sleep(3)
