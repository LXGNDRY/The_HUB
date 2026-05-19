"""
modules/compute.py — Compute Engine VM lifecycle via google-cloud-compute.
"""

from google.cloud import compute_v1


class ComputeModule:
    def __init__(self, project_id: str, credentials=None):
        self.project_id = project_id
        self.credentials = credentials
        kwargs = {"credentials": credentials} if credentials else {}
        self.instances_client = compute_v1.InstancesClient(**kwargs)

    def list_instances(self, zone: str) -> list:
        request = compute_v1.ListInstancesRequest(
            project=self.project_id, zone=zone
        )
        return list(self.instances_client.list(request=request))

    def start_instance(self, zone: str, name: str):
        request = compute_v1.StartInstanceRequest(
            project=self.project_id, zone=zone, instance=name
        )
        return self.instances_client.start(request=request).result()

    def stop_instance(self, zone: str, name: str):
        request = compute_v1.StopInstanceRequest(
            project=self.project_id, zone=zone, instance=name
        )
        return self.instances_client.stop(request=request).result()

    def delete_instance(self, zone: str, name: str):
        request = compute_v1.DeleteInstanceRequest(
            project=self.project_id, zone=zone, instance=name
        )
        return self.instances_client.delete(request=request).result()

    def get_snapshots_older_than(self, days: int = 30) -> list:
        """Return all disk snapshots older than N days."""
        import datetime
        from google.cloud import compute_v1 as cv1
        snapshots_client = cv1.SnapshotsClient(credentials=self.credentials)
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        old = []
        for s in snapshots_client.list(project=self.project_id):
            ts_str = getattr(s, "creation_timestamp", None)
            if not ts_str:
                continue
            ts = datetime.datetime.fromisoformat(ts_str[:19])
            if ts < cutoff:
                old.append(s)
        return old

    def delete_snapshot(self, snapshot_name: str):
        """Delete a disk snapshot by name."""
        from google.cloud import compute_v1 as cv1
        snapshots_client = cv1.SnapshotsClient(credentials=self.credentials)
        return snapshots_client.delete(
            project=self.project_id, snapshot=snapshot_name
        ).result()
