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
        self.compute_client = compute_v1.InstancesClient(**kwargs)
        self.project_name = f"projects/{self.project_id}"

    def get_quotas_above_threshold(self, threshold_percent: float = 80.0) -> list:
        """Return quota utilization using serviceruntime quota metrics."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=1)
        interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": int(now.timestamp())},
                "start_time": {"seconds": int(start.timestamp())},
            }
        )
        try:
            results = self.metric_client.list_time_series(
                request={
                    "name": self.project_name,
                    "filter": 'metric.type="serviceruntime.googleapis.com/quota/rate/net_usage"',
                    "interval": interval,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )
            quotas = []
            for ts in results:
                labels = ts.metric.labels
                quotas.append({
                    "quota_metric": labels.get("quota_metric", "unknown"),
                    "service": ts.resource.labels.get("service", "unknown"),
                })
            return quotas or [{"message": "No quota usage data found in the last hour."}]
        except Exception as e:
            return [{"error": str(e)}]

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
