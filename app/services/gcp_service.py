"""
GCP Infrastructure service — wraps the existing compute, billing, and storage modules.
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class GCPService:
    """Service layer wrapping existing GCP modules."""

    def __init__(self, project_id: str = "", credentials_path: str = ""):
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID", "")
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    def list_vms(self, zone: str = "us-central1-a") -> list:
        import modules.compute as compute_mod
        return compute_mod.list_instances(zone)

    def list_all_vms(self) -> list:
        import modules.compute as compute_mod
        return compute_mod.list_all_instances()

    def get_billing_info(self) -> dict:
        import modules.billing as billing_mod
        return billing_mod.get_project_billing_info()

    def get_budgets(self) -> list:
        import modules.billing as billing_mod
        return billing_mod.get_budgets()

    def check_budget(self) -> dict:
        import modules.billing as billing_mod
        return billing_mod.check_budget_status()

    def list_buckets(self) -> list:
        from modules.storage import StorageModule
        return StorageModule().list_buckets()

    def get_bucket_size(self, bucket_name: str) -> int:
        from modules.storage import StorageModule
        return StorageModule().get_bucket_size_bytes(bucket_name)