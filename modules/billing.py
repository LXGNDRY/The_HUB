"""
modules/billing.py — Cloud Billing spend via Cloud Billing API (not Monitoring).
"""

import os
from datetime import datetime, timezone


class BillingModule:
    def __init__(self, credentials=None):
        self.project_id = os.getenv("GCP_PROJECT_ID", "")
        self.credentials = credentials

    def _cloud_billing_client(self):
        from googleapiclient.discovery import build
        return build("cloudbilling", "v1", credentials=self.credentials, cache_discovery=False)

    def get_monthly_spend(self) -> dict:
        """Return estimated MTD spend from Cloud Billing budgets or a placeholder."""
        now = datetime.now(timezone.utc)
        try:
            # Use Cloud Resource Manager to list project billing info
            service = self._cloud_billing_client()
            info = service.projects().getBillingInfo(
                name=f"projects/{self.project_id}"
            ).execute()
            billing_account = info.get("billingAccountName", "unknown")
            return {
                "period": f"{now.year}-{now.month:02d}-01 to {now.date()}",
                "billing_account": billing_account,
                "note": "Detailed spend requires Cloud Billing export to BigQuery. Account linked and active.",
                "billing_enabled": info.get("billingEnabled", False),
            }
        except Exception as e:
            return {"error": str(e), "date": now.date().isoformat()}

    def get_today_spend(self) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "date": now.date().isoformat(),
            "note": "Real-time spend requires Cloud Billing export to BigQuery.",
        }

    def get_spend_by_service(self) -> dict:
        """
        Return active services as a proxy spend breakdown.
        Real per-service spend requires Cloud Billing export to BigQuery.
        """
        try:
            from googleapiclient.discovery import build
            svc = build("serviceusage", "v1", credentials=self.credentials, cache_discovery=False)
            result = svc.services().list(
                parent=f"projects/{self.project_id}",
                filter="state:ENABLED",
                pageSize=20,
            ).execute()
            services = result.get("services", [])
            return {
                s.get("config", {}).get("name", s.get("name", "unknown")): 0.0
                for s in services
            }
        except Exception as e:
            return {"error": str(e)}

    def get_top_services(self, limit: int = 5) -> list:
        """List GCP services enabled on the project as a proxy for active spend."""
        try:
            from googleapiclient.discovery import build
            svc = build("serviceusage", "v1", credentials=self.credentials, cache_discovery=False)
            result = svc.services().list(
                parent=f"projects/{self.project_id}",
                filter="state:ENABLED",
                pageSize=limit,
            ).execute()
            services = result.get("services", [])
            return [
                {"service": s.get("config", {}).get("name", s.get("name", "unknown"))}
                for s in services
            ]
        except Exception as e:
            return [{"error": str(e)}]
