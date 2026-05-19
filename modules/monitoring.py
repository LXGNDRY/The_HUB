"""
modules/monitoring.py — Cloud Monitoring: quotas and idle VM detection.
"""

import os
from datetime import datetime, timezone, timedelta
from google.cloud import monitoring_v3
from google.cloud import compute_v1


class MonitoringModule:
    def __init__(self, project_id: str, credentials=None):
        self.project_id = project_id
        kwargs = {"credentials": credentials} if credentials else {}
        self.metric_client = monitoring_v3.MetricServiceClient(**kwargs)
        self.service_client = monitoring_v3.ServiceMonitoringServiceClient(**kwargs)
        self.compute_client = compute_v1.InstancesClient(**kwargs)
        self.project_name = f"projects/{self.project_id}"

    def get_quotas_above_threshold(self, threshold_percent: float = 80.0) -> list:
        """Return quota metrics above threshold% utilization."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=10)
        interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": int(now.timestamp())},
                "start_time": {"seconds": int(start.timestamp())},
            }
        )
        results = self.metric_client.list_time_series(
            request={
                "name": self.project_name,
                "filter": 'metric.type="compute.googleapis.com/quota/exceeded"',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )
        quotas = []
        for ts in results:
            labels = ts.metric.labels
            quota_metric = labels.get("quota_metric", "unknown")
            limit_name = labels.get("limit_name", "")
            quotas.append({"quota": quota_metric, "limit": limit_name})
        return quotas or [{"message": "No quotas exceeded above threshold."}]

    def get_low_cpu_instances(
        self, threshold_percent: float = 2.0, lookback_minutes: int = 60
    ) -> list:
        """Return (name, zone) tuples for VMs with avg CPU below threshold."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=lookback_minutes)
        interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": int(now.timestamp())},
                "start_time": {"seconds": int(start.timestamp())},
            }
        )
        results = self.metric_client.list_time_series(
            request={
                "name": self.project_name,
                "filter": 'metric.type="compute.googleapis.com/instance/cpu/utilization"',
                "interval": interval,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )
        idle = []
        for ts in results:
            values = [p.value.double_value * 100 for p in ts.points]
            if values and (sum(values) / len(values)) < threshold_percent:
                labels = ts.resource.labels
                idle.append((labels.get("instance_id", "unknown"), labels.get("zone", "unknown")))
        return idle
