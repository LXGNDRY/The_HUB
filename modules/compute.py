"""
modules/compute.py — Compute Engine VM lifecycle via google-cloud-compute.
"""

from google.cloud import compute_v1


class ComputeModule:
    def __init__(self, project_id: str, credentials=None):
        self.project_id = project_id
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
