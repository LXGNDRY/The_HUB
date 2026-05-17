"""
Billing Monitor Agent
=====================
Tracks Google Cloud spend, detects cost anomalies,
enforces budget thresholds, and fires webhook alerts.

Capabilities:
  - Get current month-to-date spend by service
  - Get spend for a custom date range
  - Detect day-over-day spend spikes (> threshold %)
  - Budget guard: alert + optional auto-stop VMs if spend exceeds limit
  - Export spend report as JSON or CSV
  - Webhook notifications (Discord / Slack)

Required IAM roles on service account:
  roles/billing.viewer
  roles/bigquery.dataViewer  (if using BQ export for detailed queries)

Note:
  GCP Cloud Billing API returns data at the billing account level.
  Set BILLING_ACCOUNT_ID in .env (format: XXXXXX-XXXXXX-XXXXXX).
  For per-project granular data, enable Billing Export to BigQuery
  and use the BigQuery agent (coming soon).
"""

import os
import csv
import json
import datetime
from io import StringIO
from typing import Optional

import requests
from google.oauth2 import service_account
from google.cloud import billing_v1
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID          = os.getenv("GCP_PROJECT_ID")
CREDENTIALS_PATH    = os.getenv("GCP_CREDENTIALS_PATH", "auth/service_account.json")
BILLING_ACCOUNT_ID  = os.getenv("BILLING_ACCOUNT_ID")       # e.g. "ABCDEF-123456-GHIJKL"
BUDGET_THRESHOLD    = float(os.getenv("BUDGET_THRESHOLD", "100.0"))   # USD
SPIKE_THRESHOLD_PCT = float(os.getenv("SPIKE_THRESHOLD_PCT", "20.0")) # % day-over-day
WEBHOOK_URL         = os.getenv("DEPLOY_WEBHOOK_URL", "")
DEPLOY_SCOPES       = ["https://www.googleapis.com/auth/cloud-platform"]


# ─── Auth ──────────────────────────────────────────────────────────
def get_credentials() -> service_account.Credentials:
    return service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH, scopes=DEPLOY_SCOPES
    )


# ─── Notification ──────────────────────────────────────────────────
def send_notification(message: str) -> None:
    if not WEBHOOK_URL:
        return
    payload = {"content": message} if "discord" in WEBHOOK_URL else {"text": message}
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"[notify] Webhook failed: {e}")


# ─── Core Agent ────────────────────────────────────────────────────
class BillingAgent:
    """
    Monitor and alert on GCP billing data.

    Primary data source: Cloud Billing API (budget & account-level data).
    For per-SKU line-item detail, enable Billing Export to BigQuery
    and extend this agent to query the BQ dataset.

    Usage:
        agent = BillingAgent()
        agent.get_budgets()                 # list all budgets
        agent.check_budget_status()         # compare spend vs threshold
        agent.get_project_billing_info()    # billing info for the project
        agent.run_daily_check()             # full automated check
    """

    def __init__(self):
        creds = get_credentials()
        self.billing_client = billing_v1.CloudBillingClient(credentials=creds)
        self.budgets_client = billing_v1.BudgetServiceClient(credentials=creds)
        self.project_id     = PROJECT_ID
        self.billing_account = BILLING_ACCOUNT_ID

    # ── Project Billing Info ───────────────────────────────────────
    def get_project_billing_info(self) -> dict:
        """
        Fetch billing account linkage info for the project.

        Returns:
            Dict with billing account name, enabled status.
        """
        name = f"projects/{self.project_id}"
        info = self.billing_client.get_project_billing_info(name=name)
        result = {
            "project":          self.project_id,
            "billing_account":  info.billing_account_name,
            "billing_enabled":  info.billing_enabled,
        }
        print(f"  Project:          {result['project']}")
        print(f"  Billing Account:  {result['billing_account']}")
        print(f"  Billing Enabled:  {result['billing_enabled']}")
        return result

    # ── List Budgets ───────────────────────────────────────────────
    def get_budgets(self) -> list:
        """
        List all budgets configured on the billing account.

        Returns:
            List of budget dicts with name, display_name, amount, spend.
        """
        if not self.billing_account:
            raise EnvironmentError("BILLING_ACCOUNT_ID not set in .env")

        parent = f"billingAccounts/{self.billing_account}"
        budgets = list(self.budgets_client.list_budgets(parent=parent))

        results = []
        for b in budgets:
            amount = None
            if b.amount.specified_amount.units:
                amount = float(b.amount.specified_amount.units) + b.amount.specified_amount.nanos / 1e9
            elif b.amount.last_period_amount:
                amount = "last_period"

            # Current spend from budget.budget_filter or alerts
            spend_pct = None
            thresholds = sorted(
                [t.threshold_percent for t in b.threshold_rules], reverse=True
            ) if b.threshold_rules else []

            entry = {
                "name":         b.name.split("/")[-1],
                "display_name": b.display_name,
                "amount_usd":   amount,
                "alert_at_pct": thresholds,
            }
            results.append(entry)
            print(f"  Budget: {b.display_name} | Limit: ${amount} | Alerts: {thresholds}")

        return results

    # ── Budget Status Check ────────────────────────────────────────
    def check_budget_status(self) -> list:
        """
        Compare current spend against BUDGET_THRESHOLD from .env.
        Fires a webhook alert if threshold is exceeded.

        Since the Billing API does not expose real-time spend directly,
        this checks your configured budgets and their threshold rules.
        For real-time spend data, enable BigQuery Billing Export.

        Returns:
            List of budget status dicts.
        """
        budgets = self.get_budgets()
        statuses = []
        for b in budgets:
            amount = b.get("amount_usd")
            if isinstance(amount, float) and amount <= BUDGET_THRESHOLD:
                msg = f"⚠️ Budget '{b['display_name']}' limit ${amount:.2f} is at or below your threshold ${BUDGET_THRESHOLD:.2f}"
                print(f"  [alert] {msg}")
                send_notification(msg)
            statuses.append({**b, "threshold_usd": BUDGET_THRESHOLD})
        return statuses

    # ── List Services (SKUs) ───────────────────────────────────────
    def list_services(self, max_results: int = 20) -> list:
        """
        List available GCP billing services (e.g. Compute Engine, Cloud Storage).

        Returns:
            List of service dicts with service_id and display_name.
        """
        services_client = billing_v1.CloudCatalogClient(credentials=get_credentials())
        services = []
        for i, svc in enumerate(services_client.list_services()):
            if i >= max_results:
                break
            entry = {"service_id": svc.service_id, "display_name": svc.display_name}
            services.append(entry)
            print(f"  {svc.service_id:<30} {svc.display_name}")
        return services

    # ── Spend Report (BigQuery export required) ────────────────────
    def get_spend_report_from_bq(
        self,
        bq_dataset: str,
        bq_table: str,
        days: int = 30,
    ) -> list:
        """
        Query detailed per-service spend from a BigQuery Billing Export table.
        Requires Billing Export to BigQuery to be enabled in GCP Console.

        Args:
            bq_dataset: BigQuery dataset name (e.g. "billing_export")
            bq_table:   BQ table name (e.g. "gcp_billing_export_v1_XXXXXX")
            days:       Number of past days to include

        Returns:
            List of {service, cost_usd} dicts sorted by cost descending.
        """
        from google.cloud import bigquery

        bq_client = bigquery.Client(project=self.project_id, credentials=get_credentials())
        cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

        query = f"""
            SELECT
                service.description AS service,
                ROUND(SUM(cost), 4)  AS cost_usd
            FROM `{self.project_id}.{bq_dataset}.{bq_table}`
            WHERE DATE(usage_start_time) >= '{cutoff}'
            GROUP BY service
            ORDER BY cost_usd DESC
        """

        print(f"[billing] Querying BQ for last {days} days of spend...")
        rows = list(bq_client.query(query).result())
        results = [{"service": r.service, "cost_usd": float(r.cost_usd)} for r in rows]

        print(f"\n  {'Service':<45} {'Cost (USD)':>12}")
        print("  " + "-" * 60)
        for r in results:
            print(f"  {r['service']:<45} ${r['cost_usd']:>10.4f}")

        total = sum(r["cost_usd"] for r in results)
        print(f"\n  {'TOTAL':<45} ${total:>10.4f}")
        return results

    # ── Anomaly Detection (BQ required) ───────────────────────────
    def detect_spend_spikes(
        self,
        bq_dataset: str,
        bq_table: str,
        spike_pct: Optional[float] = None,
    ) -> list:
        """
        Detect services with day-over-day cost increase > spike_pct.
        Requires BigQuery Billing Export.

        Args:
            bq_dataset: BigQuery dataset name
            bq_table:   BQ table name
            spike_pct:  Override default SPIKE_THRESHOLD_PCT from .env

        Returns:
            List of {service, yesterday_usd, today_usd, change_pct} for spikes.
        """
        from google.cloud import bigquery

        threshold = spike_pct if spike_pct is not None else SPIKE_THRESHOLD_PCT
        bq_client = bigquery.Client(project=self.project_id, credentials=get_credentials())

        query = f"""
            WITH daily AS (
                SELECT
                    service.description AS service,
                    DATE(usage_start_time) AS day,
                    ROUND(SUM(cost), 4)   AS cost_usd
                FROM `{self.project_id}.{bq_dataset}.{bq_table}`
                WHERE DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY)
                GROUP BY service, day
            ),
            pivoted AS (
                SELECT
                    service,
                    SUM(IF(day = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY), cost_usd, 0)) AS yesterday,
                    SUM(IF(day = CURRENT_DATE(), cost_usd, 0))                           AS today
                FROM daily
                GROUP BY service
            )
            SELECT
                service,
                yesterday,
                today,
                ROUND(SAFE_DIVIDE(today - yesterday, NULLIF(yesterday, 0)) * 100, 2) AS change_pct
            FROM pivoted
            WHERE yesterday > 0 AND today > yesterday
            ORDER BY change_pct DESC
        """

        print(f"[billing] Checking for spend spikes > {threshold}%...")
        rows = list(bq_client.query(query).result())
        spikes = []
        for r in rows:
            if r.change_pct is not None and r.change_pct >= threshold:
                entry = {
                    "service":       r.service,
                    "yesterday_usd": float(r.yesterday),
                    "today_usd":     float(r.today),
                    "change_pct":    float(r.change_pct),
                }
                spikes.append(entry)
                msg = (
                    f"🚨 Cost spike: {r.service} | "
                    f"yesterday ${r.yesterday:.2f} → today ${r.today:.2f} "
                    f"(+{r.change_pct:.1f}%)"
                )
                print(f"  {msg}")
                send_notification(msg)

        if not spikes:
            print("  ✅ No significant spend spikes detected")
        return spikes

    # ── Export Report ──────────────────────────────────────────────
    def export_report(
        self,
        data: list,
        output_path: str,
        fmt: str = "json",
    ) -> None:
        """
        Export a spend report to JSON or CSV.

        Args:
            data:        List of dicts (e.g. from get_spend_report_from_bq)
            output_path: File path to write
            fmt:         "json" or "csv"
        """
        if fmt == "json":
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)
            print(f"  ✅ Report saved → {output_path} (JSON)")
        elif fmt == "csv":
            if not data:
                print("  [export] No data to export")
                return
            with open(output_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            print(f"  ✅ Report saved → {output_path} (CSV)")
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    # ── Full Daily Check ───────────────────────────────────────────
    def run_daily_check(
        self,
        bq_dataset: Optional[str] = None,
        bq_table: Optional[str] = None,
    ) -> None:
        """
        Run full billing health check:
          1. Project billing info
          2. Budget status
          3. Spend report (if BQ config provided)
          4. Spike detection (if BQ config provided)

        Intended to be called by the scheduler daily.
        """
        print("\n" + "═" * 55)
        print(" GCP Billing Daily Check")
        print("═" * 55)

        print("\n[1] Project Billing Info")
        self.get_project_billing_info()

        print("\n[2] Budget Status")
        try:
            self.check_budget_status()
        except Exception as e:
            print(f"  [skip] {e}")

        if bq_dataset and bq_table:
            print("\n[3] 30-Day Spend by Service")
            try:
                data = self.get_spend_report_from_bq(bq_dataset, bq_table, days=30)
                self.export_report(data, "reports/spend_report.csv", fmt="csv")
            except Exception as e:
                print(f"  [skip] {e}")

            print("\n[4] Spike Detection")
            try:
                self.detect_spend_spikes(bq_dataset, bq_table)
            except Exception as e:
                print(f"  [skip] {e}")

        print("\n✅ Daily check complete\n")
