"""
modules/cloud_logging.py — Cloud Logging Module

Pull structured logs from Cloud Run and other GCP services into the bot.
Enables log querying, error detection, and automated alerting based on
log patterns without needing to open Cloud Console.

Use cases:
  - Pull recent Cloud Run error logs
  - Count error rates by severity over time
  - Search logs for specific patterns (e.g. "404", "Exception")
  - Export logs to BigQuery or Sheets for analysis
  - Alert on spike in error rates

Env vars:
  GCP_PROJECT_ID — already set
  CLOUD_RUN_SERVICE_NAME — service to monitor (default: gcp-bot)
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Literal

from googleapiclient.discovery import build

logger = logging.getLogger("gcp-bot.cloud_logging")

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
SERVICE_NAME = os.getenv("CLOUD_RUN_SERVICE_NAME", "gcp-bot")
REGION = os.getenv("GCP_REGION", "us-central1")

Severity = Literal["DEFAULT", "DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY"]


class CloudLoggingModule:
    """
    Query and analyze GCP Cloud Logging for the bot's infrastructure.
    Uses the Cloud Logging API v2 (logging.googleapis.com).
    """

    def __init__(self, credentials):
        self.credentials = credentials
        self._service = None

    @property
    def service(self):
        if not self._service:
            self._service = build(
                "logging", "v2",
                credentials=self.credentials,
                cache_discovery=False,
            )
        return self._service

    # ------------------------------------------------------------------
    # Core log fetching
    # ------------------------------------------------------------------

    def fetch_logs(
        self,
        filter_str: str,
        page_size: int = 100,
        order_by: str = "timestamp desc",
    ) -> list[dict]:
        """
        Fetch log entries using a Cloud Logging filter string.

        Args:
            filter_str: Cloud Logging filter (e.g. 'severity>=ERROR resource.type="cloud_run_revision"')
            page_size:  Max entries to return per page (max 1000).
            order_by:   Sort order ("timestamp desc" or "timestamp asc").

        Returns:
            List of log entry dicts.
        """
        body = {
            "resourceNames": [f"projects/{PROJECT_ID}"],
            "filter": filter_str,
            "pageSize": page_size,
            "orderBy": order_by,
        }
        resp = self.service.entries().list(body=body).execute()
        entries = resp.get("entries", [])
        logger.info("[cloud_logging] Fetched %d log entries.", len(entries))
        return entries

    def _parse_entry(self, entry: dict) -> dict:
        """Parse a raw log entry into a clean dict."""
        ts = entry.get("timestamp", "")
        severity = entry.get("severity", "DEFAULT")
        resource = entry.get("resource", {})
        labels = resource.get("labels", {})

        # Text or JSON payload
        text = entry.get("textPayload", "")
        json_payload = entry.get("jsonPayload", {})
        if not text and json_payload:
            text = json_payload.get("message", str(json_payload))

        http_req = entry.get("httpRequest", {})

        return {
            "timestamp": ts,
            "severity": severity,
            "service": labels.get("service_name", SERVICE_NAME),
            "revision": labels.get("revision_name", ""),
            "message": text,
            "http_method": http_req.get("requestMethod", ""),
            "http_url": http_req.get("requestUrl", ""),
            "http_status": http_req.get("status", ""),
            "latency": http_req.get("latency", ""),
            "log_name": entry.get("logName", ""),
        }

    # ------------------------------------------------------------------
    # Cloud Run specific
    # ------------------------------------------------------------------

    def _cloud_run_filter(self, severity_min: str = "DEFAULT", hours_back: int = 24) -> str:
        """Build a filter string for Cloud Run logs."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        return (
            f'resource.type="cloud_run_revision" '
            f'resource.labels.service_name="{SERVICE_NAME}" '
            f'resource.labels.location="{REGION}" '
            f'severity>={severity_min} '
            f'timestamp>="{cutoff_str}"'
        )

    def get_recent_logs(self, hours_back: int = 24, limit: int = 100, severity_min: str = "DEFAULT") -> list[dict]:
        """
        Get recent logs from the Cloud Run service.

        Args:
            hours_back:   How far back to look (default 24h).
            limit:        Max entries (default 100).
            severity_min: Minimum severity level.

        Returns:
            List of parsed log entry dicts.
        """
        filter_str = self._cloud_run_filter(severity_min=severity_min, hours_back=hours_back)
        raw = self.fetch_logs(filter_str, page_size=limit)
        return [self._parse_entry(e) for e in raw]

    def get_error_logs(self, hours_back: int = 24, limit: int = 50) -> list[dict]:
        """Get ERROR and above logs from Cloud Run."""
        return self.get_recent_logs(hours_back=hours_back, limit=limit, severity_min="ERROR")

    def get_request_logs(self, hours_back: int = 24, limit: int = 100) -> list[dict]:
        """
        Get HTTP request logs (access logs) from Cloud Run.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        filter_str = (
            f'resource.type="cloud_run_revision" '
            f'resource.labels.service_name="{SERVICE_NAME}" '
            f'httpRequest.requestUrl!="" '
            f'timestamp>="{cutoff_str}"'
        )
        raw = self.fetch_logs(filter_str, page_size=limit)
        return [self._parse_entry(e) for e in raw]

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def get_error_summary(self, hours_back: int = 24) -> dict:
        """
        Summarise error counts by severity for the last N hours.

        Returns:
            {
                "time_window_hours": int,
                "total_entries": int,
                "by_severity": {"ERROR": int, "WARNING": int, ...},
                "top_errors": [{"message": str, "count": int}],
                "error_rate_per_hour": float,
            }
        """
        logs = self.get_recent_logs(hours_back=hours_back, limit=1000, severity_min="WARNING")

        by_severity: dict[str, int] = {}
        error_messages: dict[str, int] = {}

        for entry in logs:
            sev = entry.get("severity", "DEFAULT")
            by_severity[sev] = by_severity.get(sev, 0) + 1

            if sev in ("ERROR", "CRITICAL", "ALERT", "EMERGENCY"):
                msg = entry.get("message", "")[:120]  # Truncate for grouping
                error_messages[msg] = error_messages.get(msg, 0) + 1

        top_errors = sorted(
            [{"message": k, "count": v} for k, v in error_messages.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        total_errors = sum(v for k, v in by_severity.items() if k in ("ERROR", "CRITICAL", "ALERT", "EMERGENCY"))

        return {
            "time_window_hours": hours_back,
            "total_entries": len(logs),
            "by_severity": by_severity,
            "top_errors": top_errors,
            "error_count": total_errors,
            "error_rate_per_hour": round(total_errors / max(hours_back, 1), 2),
        }

    def search_logs(self, keyword: str, hours_back: int = 24, limit: int = 50) -> list[dict]:
        """
        Search logs for a specific keyword or pattern.

        Args:
            keyword:    Text to search for in log messages.
            hours_back: How far back to look.
            limit:      Max results.

        Returns:
            Matching log entries.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        filter_str = (
            f'resource.type="cloud_run_revision" '
            f'resource.labels.service_name="{SERVICE_NAME}" '
            f'timestamp>="{cutoff_str}" '
            f'textPayload:"{keyword}"'
        )
        raw = self.fetch_logs(filter_str, page_size=limit)
        logger.info("[cloud_logging] Search '%s': %d results.", keyword, len(raw))
        return [self._parse_entry(e) for e in raw]

    def get_endpoint_stats(self, hours_back: int = 24) -> list[dict]:
        """
        Analyse HTTP request logs to get per-endpoint stats.

        Returns:
            List of {"endpoint": str, "request_count": int, "error_count": int, "avg_latency_ms": float}
        """
        logs = self.get_request_logs(hours_back=hours_back, limit=1000)
        endpoint_stats: dict[str, dict] = {}

        for entry in logs:
            url = entry.get("http_url", "")
            if not url:
                continue

            # Strip query params and normalise
            path = url.split("?")[0].replace("https://", "").split("/", 1)[-1]
            path = "/" + path if not path.startswith("/") else path

            if path not in endpoint_stats:
                endpoint_stats[path] = {"request_count": 0, "error_count": 0, "latencies": []}

            endpoint_stats[path]["request_count"] += 1

            status = str(entry.get("http_status", ""))
            if status.startswith(("4", "5")):
                endpoint_stats[path]["error_count"] += 1

            latency = entry.get("latency", "")
            if latency and isinstance(latency, str) and latency.endswith("s"):
                try:
                    ms = float(latency[:-1]) * 1000
                    endpoint_stats[path]["latencies"].append(ms)
                except ValueError:
                    pass

        result = []
        for path, stats in endpoint_stats.items():
            latencies = stats["latencies"]
            result.append({
                "endpoint": path,
                "request_count": stats["request_count"],
                "error_count": stats["error_count"],
                "error_rate": round(stats["error_count"] / max(stats["request_count"], 1) * 100, 1),
                "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            })

        return sorted(result, key=lambda x: x["request_count"], reverse=True)

    # ------------------------------------------------------------------
    # Write logs (for bot internal audit trail)
    # ------------------------------------------------------------------

    def write_log(self, message: str, severity: Severity = "INFO", labels: dict = None):
        """
        Write a structured log entry to Cloud Logging.
        Use for bot audit trail / event logging.
        """
        log_name = f"projects/{PROJECT_ID}/logs/gcp-bot"
        body = {
            "entries": [
                {
                    "logName": log_name,
                    "resource": {
                        "type": "cloud_run_revision",
                        "labels": {
                            "service_name": SERVICE_NAME,
                            "location": REGION,
                            "project_id": PROJECT_ID,
                        },
                    },
                    "severity": severity,
                    "textPayload": message,
                    "labels": labels or {"source": "gcp-bot"},
                }
            ]
        }
        self.service.entries().write(body=body).execute()
        logger.info("[cloud_logging] Wrote %s log: %s", severity, message[:80])
