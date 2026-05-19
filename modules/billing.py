"""
modules/billing.py — Cloud Billing spend summaries via Cloud Monitoring.
"""

import os
from datetime import datetime, timezone, timedelta
from google.cloud import monitoring_v3


class BillingModule:
    def __init__(self, credentials=None):
        self.project_id = os.getenv("GCP_PROJECT_ID", "")
        kwargs = {"credentials": credentials} if credentials else {}
        self.client = monitoring_v3.MetricServiceClient(**kwargs)
        self.project_name = f"projects/{self.project_id}"

    def _query_cost(self, start: datetime, end: datetime) -> float:
        """Sum billing/monthly_cost metric between start and end."""
        interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": int(end.timestamp())},
                "start_time": {"seconds": int(start.timestamp())},
            }
        )
        results = self.client.list_time_series(
            request={
                "name": self.project_name,
                "filter": 'metric.type="billing.googleapis.com/billing_account/monthly_cost"',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )
        total = 0.0
        for ts in results:
            for point in ts.points:
                total += point.value.double_value
        return round(total, 4)

    def get_monthly_spend(self) -> dict:
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spend = self._query_cost(start, now)
        return {"period": f"{start.date()} to {now.date()}", "spend_usd": spend}

    def get_today_spend(self) -> dict:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        spend = self._query_cost(start, now)
        return {"date": now.date().isoformat(), "spend_usd": spend}

    def get_top_services(self, limit: int = 5) -> list:
        """Return top N services by cost this month."""
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": int(now.timestamp())},
                "start_time": {"seconds": int(start.timestamp())},
            }
        )
        results = self.client.list_time_series(
            request={
                "name": self.project_name,
                "filter": 'metric.type="billing.googleapis.com/billing_account/monthly_cost"',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )
        services = {}
        for ts in results:
            svc = ts.resource.labels.get("service", ts.metric.labels.get("service", "unknown"))
            for point in ts.points:
                services[svc] = services.get(svc, 0.0) + point.value.double_value
        top = sorted(services.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{"service": k, "spend_usd": round(v, 4)} for k, v in top]
