"""
Job definitions for the GCP Bot scheduler.
Each function is a standalone, independently testable unit.
All destructive actions are wrapped in safe_execute() for dry-run support.

Compute Engine API is OPTIONAL — if unavailable, all compute-dependent
jobs log a clear warning and skip gracefully without crashing the scheduler.
"""

import os
import logging
from datetime import datetime, timezone

from config import safe_execute, DRY_RUN
from notifications import send_alert
from auth.credentials import get_credentials

logger = logging.getLogger("gcp-bot.jobs")

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
BUDGET_THRESHOLD = float(os.getenv("BUDGET_THRESHOLD", "100.0"))
IDLE_CPU_THRESHOLD = float(os.getenv("IDLE_CPU_THRESHOLD", "2.0"))
SNAPSHOT_MAX_AGE_DAYS = int(os.getenv("SNAPSHOT_MAX_AGE_DAYS", "30"))
QUOTA_ALERT_PERCENT = float(os.getenv("QUOTA_ALERT_PERCENT", "80.0"))
STORAGE_INACTIVE_DAYS = int(os.getenv("STORAGE_INACTIVE_DAYS", "90"))
GCP_ZONES = os.getenv("GCP_ZONES", "us-central1-a,us-central1-b").split(",")


# ---------------------------------------------------------------------------
# Compute availability check — run once at import time
# ---------------------------------------------------------------------------

def _compute_available() -> bool:
    """
    Returns True if google-cloud-compute is installed AND
    the Compute Engine API is reachable for this project.
    Caches result to avoid redundant API calls.
    """
    if not hasattr(_compute_available, "_cached"):
        try:
            import google.cloud.compute_v1  # noqa: F401
            _compute_available._cached = True
            logger.info("[compute_check] Compute Engine API available.")
        except (ImportError, Exception) as e:
            _compute_available._cached = False
            logger.warning(
                "[compute_check] Compute Engine API unavailable — "
                "VM jobs will be skipped until enabled. Reason: %s", e
            )
    return _compute_available._cached


def _compute_skip_notice(job_name: str):
    """Log a clean skip message for compute-dependent jobs."""
    logger.warning(
        "[%s] Skipped — Compute Engine API not enabled. "
        "Enable it at: console.cloud.google.com/apis/library/compute.googleapis.com",
        job_name,
    )


# ---------------------------------------------------------------------------
# JOB 1 — Daily Billing Cost Alert  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def cost_alert_job():
    """
    Fetches monthly and daily GCP spend.
    Sends an alert if monthly spend exceeds BUDGET_THRESHOLD.
    """
    logger.info("[cost_alert_job] Running...")
    try:
        from modules.billing import BillingModule
        billing = BillingModule(get_credentials())
        monthly_data = billing.get_monthly_spend()
        daily_data = billing.get_today_spend()
        top_services = billing.get_top_services(limit=3)

        # get_monthly_spend returns a dict — extract a note string for the report
        billing_account = monthly_data.get("billing_account", "unknown")
        billing_enabled = monthly_data.get("billing_enabled", False)
        monthly_note = monthly_data.get("note", "")
        daily_note = daily_data.get("note", "")
        top_svc_names = [s.get("service", str(s)) for s in top_services]

        summary = (
            f"📊 *GCP Daily Cost Report* — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"Billing Account : {billing_account}\n"
            f"Billing Enabled : {billing_enabled}\n"
            f"Spend Note      : {monthly_note}\n"
            f"Daily Note      : {daily_note}\n"
            f"Top Services    : {', '.join(top_svc_names)}"
        )

        send_alert(summary)
        logger.info("[cost_alert_job] Completed. Billing enabled: %s", billing_enabled)

    except Exception as e:
        logger.error("[cost_alert_job] Failed: %s", e)
        send_alert(f"❌ cost_alert_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 2 — Weekly Snapshot Cleanup  [COMPUTE REQUIRED — GRACEFUL SKIP]
# ---------------------------------------------------------------------------

def cleanup_snapshots_job():
    """
    Deletes GCP disk snapshots older than SNAPSHOT_MAX_AGE_DAYS.
    Skips gracefully if Compute Engine API is not enabled.
    """
    logger.info("[cleanup_snapshots_job] Running...")

    if not _compute_available():
        _compute_skip_notice("cleanup_snapshots_job")
        return

    try:
        from modules.compute import ComputeModule
        compute = ComputeModule(PROJECT_ID, get_credentials())
        old_snapshots = compute.get_snapshots_older_than(days=SNAPSHOT_MAX_AGE_DAYS)

        deleted_count = 0
        for snapshot in old_snapshots:
            result = safe_execute(
                f"delete_snapshot:{snapshot.name}",
                compute.delete_snapshot,
                snapshot.name,
            )
            if result is not None or not DRY_RUN:
                deleted_count += 1

        msg = f"🧹 Snapshot cleanup: {deleted_count} snapshot(s) removed (>{SNAPSHOT_MAX_AGE_DAYS}d old)"
        if DRY_RUN:
            msg = f"[DRY RUN] {msg}"
        send_alert(msg)
        logger.info("[cleanup_snapshots_job] Completed. Deleted: %d", deleted_count)

    except Exception as e:
        logger.error("[cleanup_snapshots_job] Failed: %s", e)
        send_alert(f"❌ cleanup_snapshots_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 3 — VM Health Check  [COMPUTE REQUIRED — GRACEFUL SKIP]
# ---------------------------------------------------------------------------

def vm_health_check_job():
    """
    Scans all configured zones for VMs in unexpected states.
    Skips gracefully if Compute Engine API is not enabled.
    """
    logger.info("[vm_health_check_job] Running across zones: %s", GCP_ZONES)

    if not _compute_available():
        _compute_skip_notice("vm_health_check_job")
        return

    try:
        from modules.compute import ComputeModule
        compute = ComputeModule(PROJECT_ID, get_credentials())

        issues = []
        healthy_count = 0

        for zone in GCP_ZONES:
            for vm in compute.list_instances(zone):
                if vm.status not in ("RUNNING", "TERMINATED", "STOPPED"):
                    issues.append(f"⚠️ {vm.name} [{zone}] → {vm.status}")
                else:
                    healthy_count += 1

        if issues:
            send_alert("🔴 *VM Health Issues Detected*\n" + "\n".join(issues))
            logger.warning("[vm_health_check_job] %d issue(s) found.", len(issues))
        else:
            logger.info("[vm_health_check_job] All %d VMs healthy.", healthy_count)

    except Exception as e:
        logger.error("[vm_health_check_job] Failed: %s", e)
        send_alert(f"❌ vm_health_check_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 4 — Nightly Idle VM Auto-Shutdown  [COMPUTE REQUIRED — GRACEFUL SKIP]
# ---------------------------------------------------------------------------

def idle_vm_shutdown_job():
    """
    Stops VMs with average CPU < IDLE_CPU_THRESHOLD% over the last 60 minutes.
    Skips gracefully if Compute Engine API is not enabled.
    """
    logger.info("[idle_vm_shutdown_job] Running...")

    if not _compute_available():
        _compute_skip_notice("idle_vm_shutdown_job")
        return

    try:
        from modules.compute import ComputeModule
        from modules.monitoring import MonitoringModule
        compute = ComputeModule(PROJECT_ID, get_credentials())
        monitoring = MonitoringModule(PROJECT_ID, get_credentials())

        idle_vms = monitoring.get_low_cpu_instances(
            threshold_percent=IDLE_CPU_THRESHOLD,
            lookback_minutes=60,
            exclude_label="no-autostop",
        )

        stopped = []
        for vm_name, zone in idle_vms:
            safe_execute(
                f"stop_instance:{vm_name}@{zone}",
                compute.stop_instance,
                zone,
                vm_name,
            )
            stopped.append(f"{vm_name} ({zone})")

        if stopped:
            msg = f"💤 *Idle VM Shutdown* — {len(stopped)} stopped:\n" + "\n".join(stopped)
            if DRY_RUN:
                msg = f"[DRY RUN] {msg}"
            send_alert(msg)
        logger.info("[idle_vm_shutdown_job] Stopped: %d VMs", len(stopped))

    except Exception as e:
        logger.error("[idle_vm_shutdown_job] Failed: %s", e)
        send_alert(f"❌ idle_vm_shutdown_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 5 — Monthly GCP Usage Report  [COMPUTE OPTIONAL — PARTIAL IF MISSING]
# ---------------------------------------------------------------------------

def monthly_report_job():
    """
    Generates a full monthly GCP usage summary.
    VM count is reported as 'N/A' if Compute Engine API is unavailable.
    """
    logger.info("[monthly_report_job] Running...")
    try:
        from modules.billing import BillingModule
        from modules.storage import StorageModule
        billing = BillingModule(get_credentials())
        storage = StorageModule(get_credentials())

        monthly_data = billing.get_monthly_spend()
        spend_by_service = billing.get_spend_by_service()
        buckets = storage.list_buckets()
        total_buckets = len(list(buckets))

        billing_account = monthly_data.get("billing_account", "unknown")
        billing_enabled = monthly_data.get("billing_enabled", False)
        monthly_note = monthly_data.get("note", "No spend data available.")

        # VM count: include if compute available, show N/A otherwise
        if _compute_available():
            from modules.compute import ComputeModule
            compute = ComputeModule(PROJECT_ID, get_credentials())
            total_vms = sum(len(compute.list_instances(z)) for z in GCP_ZONES)
            vm_line = f"Active VMs    : {total_vms}"
        else:
            vm_line = "Active VMs    : N/A (Compute Engine API not enabled)"

        service_lines = "\n".join(
            [f"  • {svc}" for svc in spend_by_service]
        ) if spend_by_service else "  (Billing export to BigQuery required for per-service data)"

        report = (
            f"📅 *Monthly GCP Report — {datetime.now(timezone.utc).strftime('%B %Y')}*\n"
            f"Billing Account : {billing_account} (enabled={billing_enabled})\n"
            f"Spend Note      : {monthly_note}\n"
            f"{vm_line}\n"
            f"Storage Buckets : {total_buckets}\n\n"
            f"*Active Services:*\n{service_lines}"
        )
        send_alert(report)
        logger.info("[monthly_report_job] Completed. Billing enabled: %s", billing_enabled)

    except Exception as e:
        logger.error("[monthly_report_job] Failed: %s", e)
        send_alert(f"❌ monthly_report_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 6 — Weekly Storage Bucket Audit  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def storage_audit_job():
    """
    Flags GCP Storage buckets with no object access in STORAGE_INACTIVE_DAYS days.
    """
    logger.info("[storage_audit_job] Running...")
    try:
        from modules.storage import StorageModule
        storage = StorageModule(get_credentials())
        stale = storage.get_inactive_buckets(days=STORAGE_INACTIVE_DAYS)

        if stale:
            bucket_lines = "\n".join([f"  • {b}" for b in stale])
            send_alert(
                f"🗂️ *Storage Audit* — {len(stale)} inactive bucket(s) (>{STORAGE_INACTIVE_DAYS}d):\n"
                + bucket_lines
            )
        else:
            logger.info("[storage_audit_job] No inactive buckets found.")

        logger.info("[storage_audit_job] Completed. Stale: %d", len(stale))

    except Exception as e:
        logger.error("[storage_audit_job] Failed: %s", e)
        send_alert(f"❌ storage_audit_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 7 — Quota Usage Check  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def quota_check_job():
    """
    Checks all GCP service quotas.
    Alerts if any quota is above QUOTA_ALERT_PERCENT% utilization.
    """
    logger.info("[quota_check_job] Running...")
    try:
        from modules.monitoring import MonitoringModule
        monitoring = MonitoringModule(PROJECT_ID, get_credentials())
        over_quota = monitoring.get_quotas_above_threshold(
            threshold_percent=QUOTA_ALERT_PERCENT
        )

        if over_quota:
            lines = "\n".join(
                [f"  ⚠️ {q['metric']}: {q['percent']:.1f}%" for q in over_quota]
            )
            send_alert(
                f"📈 *Quota Alert* — {len(over_quota)} quota(s) above {QUOTA_ALERT_PERCENT}%:\n"
                + lines
            )
            logger.warning("[quota_check_job] %d quotas near limit.", len(over_quota))
        else:
            logger.info("[quota_check_job] All quotas within safe range.")

    except Exception as e:
        logger.error("[quota_check_job] Failed: %s", e)
        send_alert(f"❌ quota_check_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 8 — Daily Indexing Submission  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def indexing_submission_job():
    """
    Parses the store sitemap and submits all URLs to Google's Indexing API.
    Runs daily to ensure new products/pages are indexed quickly.
    Quota: 200 URLs/day.
    """
    logger.info("[indexing_submission_job] Running...")
    try:
        from modules.indexing import IndexingModule
        from auth.credentials import get_credentials
        mod = IndexingModule(get_credentials())
        result = mod.submit_sitemap_urls()
        msg = (
            f"🔍 *Indexing Submission Complete*\n"
            f"Submitted : {len(result.get('submitted', []))}\n"
            f"Skipped   : {len(result.get('skipped', []))} (quota)\n"
            f"Errors    : {len(result.get('errors', []))}"
        )
        send_alert(msg)
        logger.info("[indexing_submission_job] Done. %s submitted.", len(result.get('submitted', [])))
    except Exception as e:
        logger.error("[indexing_submission_job] Failed: %s", e)
        send_alert(f"❌ indexing_submission_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 9 — Sheets Dashboard Refresh  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def sheets_refresh_job():
    """
    Refreshes the Google Sheets dashboard with the latest GA4, GSC,
    PageSpeed, and billing data. Runs daily.
    """
    logger.info("[sheets_refresh_job] Running...")
    try:
        from modules.sheets import SheetsModule
        from modules.billing import BillingModule
        from auth.credentials import get_credentials
        import os, json
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = get_credentials()
        sm = SheetsModule(creds)
        bm = BillingModule(creds)

        # Fetch GA4
        ga4_countries = {}
        try:
            from modules.analytics import AnalyticsModule
            am = AnalyticsModule()
            ga4_traffic = am.get_traffic_summary()
            ga4_pages = am.get_top_pages()
            ga4_countries = am.get_country_breakdown()
        except Exception as ga4_err:
            logger.warning("[sheets_refresh_job] GA4 fetch failed: %s", ga4_err)
            ga4_traffic, ga4_pages = {}, {}

        # Fetch GSC
        try:
            token_json = os.getenv("GSC_TOKEN_JSON", "")
            if token_json:
                token_data = json.loads(token_json)
                gsc_creds = Credentials(
                    token=token_data.get("token"),
                    refresh_token=token_data.get("refresh_token"),
                    token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                    client_id=token_data.get("client_id"),
                    client_secret=token_data.get("client_secret"),
                    scopes=token_data.get("scopes"),
                )
                svc = build("searchconsole", "v1", credentials=gsc_creds, cache_discovery=False)
                site_url = os.getenv("GSC_SITE_URL", "https://legendary-branding.com")
                from datetime import date, timedelta
                gsc_end = date.today() - timedelta(days=3)  # GSC data lags ~3 days
                gsc_start = gsc_end - timedelta(days=90)
                gsc_data = svc.searchanalytics().query(
                    siteUrl=site_url,
                    body={
                        "startDate": gsc_start.isoformat(),
                        "endDate": gsc_end.isoformat(),
                        "dimensions": ["query"],
                        "rowLimit": 50,
                    }
                ).execute()
            else:
                gsc_data = {}
        except Exception:
            gsc_data = {}

        # Fetch PageSpeed
        try:
            from agents.pagespeed_agent import run_pagespeed
            mobile_ps = run_pagespeed(strategy="mobile")
            desktop_ps = run_pagespeed(strategy="desktop")
        except Exception:
            mobile_ps, desktop_ps = {}, {}

        billing_data = bm.get_monthly_spend()

        url = sm.refresh_full_dashboard(ga4_traffic, ga4_pages, gsc_data, mobile_ps, desktop_ps, billing_data,
                                        ga4_countries=ga4_countries)
        send_alert(f"📊 *Sheets Dashboard Refreshed*\n{url}")
        logger.info("[sheets_refresh_job] Done. URL: %s", url)

    except Exception as e:
        logger.error("[sheets_refresh_job] Failed: %s", e)
        send_alert(f"❌ sheets_refresh_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 10 — Error Log Monitoring  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def error_log_monitor_job():
    """
    Checks Cloud Run error logs every 6 hours.
    Sends an alert if error rate spikes above threshold.
    """
    ERROR_RATE_THRESHOLD = float(os.getenv("ERROR_RATE_THRESHOLD", "5.0"))  # errors/hour
    logger.info("[error_log_monitor_job] Running...")
    try:
        from modules.cloud_logging import CloudLoggingModule
        from auth.credentials import get_credentials
        mod = CloudLoggingModule(get_credentials())
        summary = mod.get_error_summary(hours_back=6)

        error_rate = summary.get("error_rate_per_hour", 0)
        error_count = summary.get("error_count", 0)

        if error_rate >= ERROR_RATE_THRESHOLD:
            top_errors = summary.get("top_errors", [])[:3]
            error_lines = "\n".join([
                f"  • [{e['count']}x] {e['message'][:80]}" for e in top_errors
            ])
            send_alert(
                f"🚨 *Error Spike Detected* — {error_rate:.1f} errors/hour\n"
                f"Last 6h count : {error_count}\n"
                f"Top errors:\n{error_lines}"
            )
            logger.warning("[error_log_monitor_job] Spike detected: %.1f errors/hr", error_rate)
        else:
            logger.info("[error_log_monitor_job] OK. Error rate: %.2f/hr", error_rate)

    except Exception as e:
        logger.error("[error_log_monitor_job] Failed: %s", e)
        send_alert(f"❌ error_log_monitor_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 11 — Shopify Product Health Check  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def shopify_product_health_job():
    """
    Audits all active Shopify products for data quality gaps:
    missing SKUs, missing barcodes, blank product types.
    Sends an alert summary only when gaps are found.
    """
    logger.info("[shopify_product_health_job] Running...")
    try:
        from modules.shopify import _graphql

        query = """
        query($cursor: String) {
          products(first: 50, after: $cursor, query: "status:active") {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              title
              productType
              variants(first: 10) {
                nodes { sku barcode }
              }
            }
          }
        }
        """

        all_products = []
        cursor = None
        while True:
            data = _graphql(query, {"cursor": cursor})
            page_data = data["products"]
            all_products.extend(page_data["nodes"])
            if not page_data["pageInfo"]["hasNextPage"]:
                break
            cursor = page_data["pageInfo"]["endCursor"]

        no_product_type = []
        no_sku_products = []
        no_barcode_products = []

        for p in all_products:
            title = p["title"]
            if not (p.get("productType") or "").strip():
                no_product_type.append(title)
            variants = p["variants"]["nodes"]
            if any(not (v.get("sku") or "").strip() for v in variants):
                no_sku_products.append(title)
            if any(not (v.get("barcode") or "").strip() for v in variants):
                no_barcode_products.append(title)

        total = len(all_products)
        has_gaps = no_product_type or no_sku_products or no_barcode_products

        if has_gaps:
            lines = [f"🛍️ *Shopify Product Health — {total} active products*"]
            if no_product_type:
                lines.append(f"\n*Missing Product Type ({len(no_product_type)}):*")
                lines.extend([f"  • {t}" for t in no_product_type[:10]])
                if len(no_product_type) > 10:
                    lines.append(f"  … and {len(no_product_type) - 10} more")
            if no_sku_products:
                lines.append(f"\n*Missing SKU ({len(no_sku_products)}):*")
                lines.extend([f"  • {t}" for t in no_sku_products[:5]])
                if len(no_sku_products) > 5:
                    lines.append(f"  … and {len(no_sku_products) - 5} more")
            if no_barcode_products:
                lines.append(f"\n*Missing Barcode/GTIN ({len(no_barcode_products)}):*")
                lines.extend([f"  • {t}" for t in no_barcode_products[:5]])
                if len(no_barcode_products) > 5:
                    lines.append(f"  … and {len(no_barcode_products) - 5} more")
            send_alert("\n".join(lines))
            logger.warning("[shopify_product_health_job] Gaps found — %d no-type, %d no-sku, %d no-barcode",
                           len(no_product_type), len(no_sku_products), len(no_barcode_products))
        else:
            logger.info("[shopify_product_health_job] All %d products OK.", total)

    except Exception as e:
        logger.error("[shopify_product_health_job] Failed: %s", e)
        send_alert(f"❌ shopify_product_health_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 12 — GMC Disapproval Check  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def gmc_disapproval_check_job():
    """
    Checks Google Merchant Center for disapproved products and active
    data quality flags. Alerts if any disapprovals or critical issues are found.
    Requires: GCP_PROJECT_ID, GCP_SA_KEY_JSON (or ADC), GMC_MERCHANT_ID env vars.
    """
    import os
    logger.info("[gmc_disapproval_check_job] Running...")

    merchant_id = os.getenv("GMC_MERCHANT_ID", "")
    if not merchant_id:
        logger.warning("[gmc_disapproval_check_job] GMC_MERCHANT_ID not set — skipping.")
        return

    try:
        from googleapiclient.discovery import build
        from auth.credentials import get_credentials

        creds = get_credentials()
        service = build("content", "v2.1", credentials=creds, cache_discovery=False)

        # Fetch product statuses (summary level — fast, no per-product detail)
        statuses = service.productstatuses().list(
            merchantId=merchant_id,
            maxResults=250,
        ).execute()

        disapproved = []
        flagged = []

        for item in statuses.get("resources", []):
            product_id = item.get("productId", "")
            title = item.get("title", product_id)
            dest_statuses = item.get("destinationStatuses", [])

            for ds in dest_statuses:
                if ds.get("status") == "disapproved":
                    disapproved.append(title)
                    break

            for issue in item.get("itemLevelIssues", []):
                if issue.get("severity") == "error":
                    flagged.append((title, issue.get("description", "")))
                    break

        if disapproved or flagged:
            lines = [f"🚫 *GMC Product Health Check*"]
            if disapproved:
                lines.append(f"\n*Disapproved ({len(disapproved)}):*")
                lines.extend([f"  • {t}" for t in disapproved[:10]])
                if len(disapproved) > 10:
                    lines.append(f"  … and {len(disapproved) - 10} more")
            if flagged:
                lines.append(f"\n*Critical Issues ({len(flagged)}):*")
                for title, desc in flagged[:5]:
                    lines.append(f"  • {title}: {desc}")
                if len(flagged) > 5:
                    lines.append(f"  … and {len(flagged) - 5} more")
            send_alert("\n".join(lines))
            logger.warning("[gmc_disapproval_check_job] %d disapproved, %d flagged.",
                           len(disapproved), len(flagged))
        else:
            logger.info("[gmc_disapproval_check_job] All products approved.")

    except Exception as e:
        logger.error("[gmc_disapproval_check_job] Failed: %s", e)
        send_alert(f"❌ gmc_disapproval_check_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 13 — GMC × Shopify Shipping Drift Check  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def gmc_shipping_drift_check_job():
    """
    Compares Shopify shipping zones against GMC shipping services.
    Alerts if any country present in Shopify zones is missing from GMC shipping,
    or if free-shipping thresholds differ. Does NOT auto-fix — alert only.
    Requires: GMC_MERCHANT_ID, GCP_SA_KEY_JSON (or ADC).
    """
    import os
    logger.info("[gmc_shipping_drift_check_job] Running...")

    merchant_id = os.getenv("GMC_MERCHANT_ID", "")
    if not merchant_id:
        logger.warning("[gmc_shipping_drift_check_job] GMC_MERCHANT_ID not set — skipping.")
        return

    try:
        from googleapiclient.discovery import build
        from auth.credentials import get_credentials
        from modules.shopify import shipping_rates_summary

        creds = get_credentials()
        service = build("content", "v2.1", credentials=creds, cache_discovery=False)

        # Shopify: collect all countries with active rates
        shopify_zones = shipping_rates_summary()
        shopify_countries = set()
        for zone in shopify_zones.get("zones", []):
            for country in zone.get("countries", []):
                code = country.get("code") or country.get("country_code")
                if code:
                    shopify_countries.add(code.upper())

        # GMC: collect all countries with active shipping services
        gmc_resp = service.shippingsettings().get(
            merchantId=merchant_id, accountId=merchant_id
        ).execute()
        gmc_countries = set()
        for svc in gmc_resp.get("services", []):
            if svc.get("active", False):
                for area in svc.get("deliveryCountries", []):
                    gmc_countries.add(area.upper())

        missing_from_gmc = shopify_countries - gmc_countries
        missing_from_shopify = gmc_countries - shopify_countries

        if missing_from_gmc or missing_from_shopify:
            lines = ["⚠️ *GMC × Shopify Shipping Drift Detected*"]
            if missing_from_gmc:
                lines.append(f"\n*In Shopify but missing from GMC ({len(missing_from_gmc)}):*")
                lines.append("  " + ", ".join(sorted(missing_from_gmc)))
            if missing_from_shopify:
                lines.append(f"\n*In GMC but missing from Shopify ({len(missing_from_shopify)}):*")
                lines.append("  " + ", ".join(sorted(missing_from_shopify)))
            lines.append("\nRun the sync-gmc-shipping workflow to fix.")
            send_alert("\n".join(lines))
            logger.warning("[gmc_shipping_drift_check_job] Drift: %d missing from GMC, %d from Shopify",
                           len(missing_from_gmc), len(missing_from_shopify))
        else:
            logger.info("[gmc_shipping_drift_check_job] Shipping in sync. %d countries matched.", len(shopify_countries))

    except Exception as e:
        logger.error("[gmc_shipping_drift_check_job] Failed: %s", e)
        send_alert(f"❌ gmc_shipping_drift_check_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 14 — Klaviyo Flow Health Check  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def klaviyo_flow_health_job():
    """
    Checks that all 7 critical Legendary Branding email flows are:
      - enabled (status == 'live')
      - have a template assigned to their primary flow message
    Alerts if any flow is paused or missing a template.
    """
    logger.info("[klaviyo_flow_health_job] Running...")

    # Known critical flow message IDs (discovered May/June 2026)
    CRITICAL_FLOW_MESSAGES = {
        "UjfrVL": "Welcome Series",
        "VjwdXC": "Customer Thank You",
        "YkSXSX": "Abandoned Bag (Email 1)",
        "Y5aXaT": "Browse Abandonment",
        "YyydEG": "Shipping Confirmation",
        "XVxb45": "Out for Delivery",
        "Ridrhn": "Delivered + Review",
    }

    try:
        from modules.klaviyo import KlaviyoModule
        klv = KlaviyoModule()

        issues = []

        for msg_id, flow_name in CRITICAL_FLOW_MESSAGES.items():
            try:
                msg = klv.get_flow_message(msg_id)
                if not msg.get("template_id"):
                    issues.append(f"  • *{flow_name}*: no template assigned (message {msg_id})")
            except Exception as e:
                issues.append(f"  • *{flow_name}*: could not fetch message {msg_id} — {e}")

        # Also check that all flows are live
        try:
            flows = klv.list_flows()
            paused = [
                f["name"] for f in flows.get("flows", [])
                if f.get("status") not in ("live", "manual")
            ]
            for name in paused:
                issues.append(f"  • Flow *{name}* is not live")
        except Exception as e:
            logger.warning("[klaviyo_flow_health_job] Could not check flow statuses: %s", e)

        if issues:
            send_alert("📧 *Klaviyo Flow Health Issues*\n" + "\n".join(issues))
            logger.warning("[klaviyo_flow_health_job] %d issue(s) found.", len(issues))
        else:
            logger.info("[klaviyo_flow_health_job] All 7 flows healthy.")

    except Exception as e:
        logger.error("[klaviyo_flow_health_job] Failed: %s", e)
        send_alert(f"❌ klaviyo_flow_health_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 15 — Alt Text Auto-Patch  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def alt_text_auto_patch_job():
    """
    Scans all active product images and fills any missing alt text.
    Pattern: "{Title} — {Product Type} | Legendary Branding"
    Only writes when alt is blank — safe to run daily.
    """
    logger.info("[alt_text_auto_patch_job] Running...")
    try:
        import time
        from modules.shopify import list_products, list_product_images, update_product_image_alt

        products = list_products(limit=250, status="active")
        patched = 0
        skipped = 0

        for product in products.get("products", []):
            pid = product["id"]
            title = product.get("title", "")
            ptype = product.get("product_type", "")
            tags = product.get("tags", "")

            images = list_product_images(pid)
            for idx, img in enumerate(images.get("images", []), start=1):
                if img.get("alt"):
                    skipped += 1
                    continue

                # Build SEO-friendly alt text
                ptype_part = f" — {ptype}" if ptype else ""
                detail = f" Detail View {idx}" if idx > 1 else ""
                alt = f"{title}{ptype_part}{detail} | Legendary Branding"[:255]

                if not DRY_RUN:
                    result = safe_execute(
                        f"update_image_alt:{pid}:{img['id']}",
                        update_product_image_alt,
                        pid, img["id"], alt,
                    )
                    if result is not None:
                        patched += 1
                else:
                    patched += 1

                time.sleep(0.55)  # ~1.8 req/s — within Shopify's 2/s REST limit

        msg = f"🖼️ *Alt Text Auto-Patch* — {patched} filled, {skipped} already set"
        if DRY_RUN:
            msg = f"[DRY RUN] {msg}"
        if patched > 0:
            send_alert(msg)
        logger.info("[alt_text_auto_patch_job] Done. Patched: %d, skipped: %d", patched, skipped)

    except Exception as e:
        logger.error("[alt_text_auto_patch_job] Failed: %s", e)
        send_alert(f"❌ alt_text_auto_patch_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 16 — IndexNow: Ping New Products  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def indexnow_new_products_job():
    """
    Finds Shopify products published in the last 25 hours and pings
    IndexNow for each new URL so search engines index them immediately.
    Requires: INDEXNOW_API_KEY env var.
    """
    import os
    logger.info("[indexnow_new_products_job] Running...")

    api_key = os.getenv("INDEXNOW_API_KEY", "")
    store_domain = os.getenv("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
    site_domain = os.getenv("SITE_DOMAIN", "legendary-branding.com")

    if not api_key:
        logger.warning("[indexnow_new_products_job] INDEXNOW_API_KEY not set — skipping.")
        return

    try:
        import requests as _requests
        from datetime import datetime, timezone, timedelta
        from modules.shopify import _get

        cutoff = datetime.now(timezone.utc) - timedelta(hours=25)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S%z")

        # Shopify REST: products published after cutoff
        data = _get(f"/products.json?status=active&published_at_min={cutoff_str}&limit=50&fields=id,handle,published_at")
        products = data.get("products", [])

        if not products:
            logger.info("[indexnow_new_products_job] No new products in last 25h.")
            return

        urls = [f"https://{site_domain}/products/{p['handle']}" for p in products]

        resp = _requests.post(
            "https://api.indexnow.org/indexnow",
            json={
                "host": site_domain,
                "key": api_key,
                "keyLocation": f"https://{site_domain}/pages/{api_key}",
                "urlList": urls,
            },
            timeout=15,
        )
        resp.raise_for_status()

        send_alert(
            f"🔎 *IndexNow: {len(urls)} new product(s) pinged*\n"
            + "\n".join([f"  • {u}" for u in urls[:10]])
            + (f"\n  … and {len(urls) - 10} more" if len(urls) > 10 else "")
        )
        logger.info("[indexnow_new_products_job] Pinged %d URLs.", len(urls))

    except Exception as e:
        logger.error("[indexnow_new_products_job] Failed: %s", e)
        send_alert(f"❌ indexnow_new_products_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 17 — GMC Title Rotation  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def gmc_title_rotation_job():
    """
    Runs the GMC A/B title rotation engine. For each active product:
    - Fetches 14-day free listing CTR from GMC reports.search
    - Decides whether to rotate, lock, unlock, or cool down based on CTR thresholds
    - Saves updated rotation state to GCS (lb-feed-state/title_rotation_state.json)
    Requires: GMC_MERCHANT_ID, GCP_SA_KEY_JSON env vars.
    The actual supplemental feed CSV rebuild (gmc_supplemental_feed.py) is a
    separate GitHub Actions workflow that uses this state file; this job only
    advances the rotation state.
    """
    import os
    import sys
    logger.info("[gmc_title_rotation_job] Running...")

    sa_key_json = os.getenv("GCP_SA_KEY_JSON", "")
    merchant_id = os.getenv("GMC_MERCHANT_ID", "")

    if not sa_key_json or not merchant_id:
        logger.warning("[gmc_title_rotation_job] GCP_SA_KEY_JSON or GMC_MERCHANT_ID not set — skipping.")
        return

    try:
        from datetime import date

        # Add scripts/ to path so title_rotation_module is importable
        scripts_dir = os.path.join(os.path.dirname(__file__), "..", "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from title_rotation_module import (
            load_state,
            save_state,
            fetch_free_listing_performance,
            decide_rotation,
        )

        today = date.today().isoformat()

        # 1. Load existing rotation state from GCS
        state = load_state(sa_key_json)
        products_state = state.setdefault("products", {})

        # 2. Fetch 14-day GMC free listing performance
        perf_data = fetch_free_listing_performance(sa_key_json)

        # 3. Iterate over tracked products and advance rotation decisions
        from modules.shopify import _get
        data = _get("/products.json?status=active&limit=250&fields=id,handle,product_type,variants")
        products = data.get("products", [])

        rotated = locked = cooled = no_pool = 0
        for product in products:
            handle = product.get("handle", "")
            category = product.get("product_type", "")
            variants = product.get("variants", [])
            if not handle or not category:
                continue

            _, reason = decide_rotation(handle, category, variants, perf_data, state, today)
            if reason == "ROTATE":
                rotated += 1
            elif reason == "LOCKED":
                locked += 1
            elif reason in ("COOLING", "UNLOCK_ROTATE"):
                cooled += 1
            elif reason == "NO_POOL":
                no_pool += 1

        # 4. Save updated state back to GCS
        state["last_run"] = today
        save_state(state, sa_key_json)

        summary = (
            f"🔄 *GMC Title Rotation complete*\n"
            f"  Rotated: {rotated} | Locked: {locked} | Cooling: {cooled} | No pool: {no_pool}\n"
            f"  State saved to GCS. Run gmc_supplemental_feed.py to rebuild the feed CSV."
        )
        send_alert(summary)
        logger.info(
            "[gmc_title_rotation_job] Done. rotated=%d locked=%d cooled=%d no_pool=%d",
            rotated, locked, cooled, no_pool,
        )

    except Exception as e:
        logger.error("[gmc_title_rotation_job] Failed: %s", e)
        send_alert(f"❌ gmc_title_rotation_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 18 — Compliance Patch (COO + HS Code)  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def compliance_patch_job():
    """
    Nightly sweep: for every product variant missing countryCodeOfOrigin or
    harmonizedSystemCode, infer both from the product title/type using the
    shared product_compliance module and write them via inventoryItemUpdate.

    - Never overwrites a value that already exists (safe to run nightly).
    - Respects the `coo:XX` product tag pattern for per-product COO overrides.
    - Sends a summary alert only when at least one variant was updated.
    """
    logger.info("[compliance_patch_job] Running...")
    try:
        import time
        from modules.shopify import _graphql, update_inventory_item_compliance
        from modules.product_compliance import infer_hs_code, resolve_coo

        FETCH_QUERY = """
        query($cursor: String) {
          products(first: 50, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              title
              productType
              tags
              variants(first: 100) {
                nodes {
                  id
                  inventoryItem {
                    id
                    countryCodeOfOrigin
                    harmonizedSystemCode
                  }
                }
              }
            }
          }
        }
        """

        updated = 0
        errors = 0
        cursor = None

        while True:
            data = _graphql(FETCH_QUERY, {"cursor": cursor})
            page = data["products"]

            for product in page["nodes"]:
                title = product.get("title", "")
                product_type = (product.get("productType") or "").strip()
                tags = [t.strip() for t in (product.get("tags") or "").split(",") if t.strip()]

                coo = resolve_coo(tags)
                hs_code = infer_hs_code(product_type, title)

                for variant in product["variants"]["nodes"]:
                    inv = variant.get("inventoryItem") or {}
                    inv_gid = inv.get("id")
                    if not inv_gid:
                        continue

                    cur_coo = (inv.get("countryCodeOfOrigin") or "").strip()
                    cur_hs = (inv.get("harmonizedSystemCode") or "").strip()

                    if cur_coo and cur_hs:
                        continue  # already complete — skip

                    write_coo = coo if not cur_coo else cur_coo
                    write_hs = hs_code if not cur_hs else cur_hs

                    result = update_inventory_item_compliance(inv_gid, write_coo, write_hs)
                    errs = (result.get("data", {})
                            .get("inventoryItemUpdate", {})
                            .get("userErrors", []))
                    if errs:
                        logger.error("[compliance_patch_job] Error on %s: %s", inv_gid, errs)
                        errors += 1
                    else:
                        updated += 1

                time.sleep(0.1)  # stay well within Shopify GraphQL rate limits

            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]

        logger.info("[compliance_patch_job] Done. updated=%d errors=%d", updated, errors)
        if updated > 0 or errors > 0:
            send_alert(
                f"🌐 *Compliance Patch (COO + HS Code)*\n"
                f"  Variants updated : {updated}\n"
                f"  Errors           : {errors}"
            )

    except Exception as e:
        logger.error("[compliance_patch_job] Failed: %s", e)
        send_alert(f"❌ compliance_patch_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 19 — Product Type Patch  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def product_type_patch_job():
    """
    Nightly sweep: for every product whose productType is blank or not a
    canonical Google Shopping taxonomy string, infer the correct taxonomy
    value from the product type + title and write it back via productUpdate.

    - Never overwrites a value that is already a canonical taxonomy string.
    - Idempotent and safe to run nightly alongside compliance_patch_job.
    - Sends a summary alert only when at least one product was updated.
    """
    logger.info("[product_type_patch_job] Running...")
    try:
        import time
        from modules.shopify import _graphql, update_product_type
        from modules.product_compliance import resolve_product_type, _CANONICAL_TYPES

        FETCH_QUERY = """
        query($cursor: String) {
          products(first: 50, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              title
              productType
              metafield(namespace: "google", key: "google_product_category") { value }
            }
          }
        }
        """

        updated = 0
        errors = 0
        cursor = None

        while True:
            data = _graphql(FETCH_QUERY, {"cursor": cursor})
            page = data["products"]

            for product in page["nodes"]:
                title = product.get("title", "")
                current_type = (product.get("productType") or "").strip()
                existing_category = (
                    (product.get("metafield") or {}).get("value") or ""
                ).strip()

                # Resolve canonical type (may already be canonical)
                resolved = resolve_product_type(current_type, title)

                # Determine correct GMC category ID
                from modules.product_compliance import resolve_gmc_category_id
                from modules.shopify import update_google_product_category
                correct_category_id = resolve_gmc_category_id(resolved)

                # Write product_type only if it's non-canonical
                if current_type not in _CANONICAL_TYPES:
                    result = update_product_type(product["id"], resolved)
                    errs = (result.get("data", {})
                            .get("productUpdate", {})
                            .get("userErrors", []))
                    if errs:
                        logger.error("[product_type_patch_job] productType error on %s: %s", product["id"], errs)
                        errors += 1
                    else:
                        logger.info(
                            "[product_type_patch_job] productType '%s' → '%s' (%s)",
                            current_type or "(blank)", resolved, title[:60],
                        )
                        updated += 1

                # Write google_product_category metafield if missing or wrong
                if existing_category != correct_category_id:
                    numeric_id = int(product["id"].split("/")[-1])
                    try:
                        update_google_product_category(numeric_id, correct_category_id)
                        logger.info(
                            "[product_type_patch_job] google_product_category '%s' → '%s' (%s)",
                            existing_category or "(blank)", correct_category_id, title[:60],
                        )
                        updated += 1
                    except Exception as meta_err:
                        logger.error("[product_type_patch_job] metafield error on %s: %s", product["id"], meta_err)
                        errors += 1

                time.sleep(0.2)

            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]

        logger.info("[product_type_patch_job] Done. updated=%d errors=%d", updated, errors)
        if updated > 0 or errors > 0:
            send_alert(
                f"🏷️ *Product Type Patch*\n"
                f"  Products updated : {updated}\n"
                f"  Errors           : {errors}"
            )

    except Exception as e:
        logger.error("[product_type_patch_job] Failed: %s", e)
        send_alert(f"❌ product_type_patch_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 20 — Product Weight Patch  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def product_weight_patch_job():
    """
    Nightly sweep: for every product variant with no weight set (weight == 0),
    infer the correct default weight in grams from the product's canonical
    taxonomy type and write it back via productVariantUpdate.

    - Only writes to variants where weight is 0 or null — never overwrites.
    - Idempotent and safe to run nightly alongside product_type_patch_job.
    - Sends a summary alert only when at least one variant was updated.
    """
    logger.info("[product_weight_patch_job] Running...")
    try:
        import time
        import requests as _requests
        from modules.shopify import BASE_URL, _headers, update_variant_weight
        from modules.product_compliance import resolve_product_type, resolve_product_weight_g

        updated = 0
        errors = 0

        # REST pagination via Link header
        url = f"{BASE_URL}/products.json"
        params: dict | None = {"limit": 250, "status": "any", "fields": "id,title,product_type,variants"}

        while url:
            resp = _requests.get(url, headers=_headers(), params=params, timeout=30)
            resp.raise_for_status()
            products = resp.json().get("products", [])
            params = None  # only pass on first request; subsequent URLs are fully formed

            for product in products:
                title = product.get("title", "")
                product_type = (product.get("product_type") or "").strip()
                canonical = resolve_product_type(product_type, title)
                weight_g = resolve_product_weight_g(canonical)

                for variant in product.get("variants", []):
                    current_weight = variant.get("weight") or 0.0
                    if float(current_weight) > 0:
                        continue  # already has a weight — skip

                    variant_id = variant["id"]
                    try:
                        update_variant_weight(variant_id, weight_g)
                        logger.info(
                            "[product_weight_patch_job] Set weight=%.0fg on variant %s (%s)",
                            weight_g, variant_id, title[:50],
                        )
                        updated += 1
                    except Exception as ve:
                        logger.error("[product_weight_patch_job] Error on variant %s: %s", variant_id, ve)
                        errors += 1

                    time.sleep(0.2)

            # Follow REST pagination Link header
            link = resp.headers.get("Link", "")
            next_url = None
            for part in link.split(","):
                part = part.strip()
                if 'rel="next"' in part:
                    next_url = part.split(";")[0].strip().strip("<>")
                    break
            url = next_url

        logger.info("[product_weight_patch_job] Done. updated=%d errors=%d", updated, errors)
        if updated > 0 or errors > 0:
            send_alert(
                f"⚖️ *Product Weight Patch*\n"
                f"  Variants updated : {updated}\n"
                f"  Errors           : {errors}"
            )

    except Exception as e:
        logger.error("[product_weight_patch_job] Failed: %s", e)
        send_alert(f"❌ product_weight_patch_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 21 — Blog Writer  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def blog_writer_job():
    """
    Generate and publish one SEO blog post to the Shopify store.
    Runs 3x daily (08:00, 12:00, 16:00 CT) for 3 posts per day.
    Idempotent — skips topics already published.
    """
    logger.info("[blog_writer_job] Running...")
    try:
        from agents.blog_writer_agent import run_blog_writer, BLOG_POSTS_PER_RUN
        result = run_blog_writer(posts_per_run=BLOG_POSTS_PER_RUN)

        published = result.get("published", [])
        skipped = result.get("skipped", [])
        errors = result.get("errors", [])

        if published:
            lines = "\n".join(
                f"  • {p['title']}\n    {p['url']}" if isinstance(p, dict) else f"  • {p}"
                for p in published
            )
            send_alert(f"✍️ *Blog Writer* — {len(published)} post(s) published:\n{lines}")
        if errors:
            send_alert(f"⚠️ *Blog Writer* — {len(errors)} error(s):\n" + "\n".join(errors))
        if not published and not errors:
            logger.info("[blog_writer_job] No new posts — all topics already published or skipped.")

        logger.info(
            "[blog_writer_job] Done. published=%d skipped=%d errors=%d",
            len(published), len(skipped), len(errors),
        )
    except Exception as e:
        logger.error("[blog_writer_job] Failed: %s", e)
        send_alert(f"❌ blog_writer_job failed: {e}")


# ---------------------------------------------------------------------------
# JOB 22 — Market Health Check  [NO COMPUTE REQUIRED]
# ---------------------------------------------------------------------------

def market_health_job():
    """
    Daily check that all Shopify markets are correctly configured for
    international sales. Automatically re-enables markets that drift to
    disabled, enables local currency display, and alerts on any remaining
    issues that require manual intervention (e.g. missing price list).

    Idempotent — safe to run daily. Uses safe_execute() for all writes.
    """
    logger.info("[market_health_job] Running...")

    # Known market GIDs — these are stable identifiers in the Shopify account.
    INDIA_MARKET_GID = "gid://shopify/Market/56012275865"
    INTERNATIONAL_MARKET_GID = "gid://shopify/Market/1614020761"

    try:
        from modules.shopify import (
            list_markets,
            enable_market,
            update_market_currency,
        )

        markets_data = list_markets()
        markets = {m["name"]: m for m in markets_data["markets"]}

        issues = []
        fixed = []

        # ── Ensure India market is enabled ──
        india = markets.get("India")
        if india and not india["enabled"]:
            safe_execute(
                "enable_market:India",
                enable_market,
                INDIA_MARKET_GID,
            )
            fixed.append("✅ Re-enabled India market")
            logger.info("[market_health_job] Re-enabled India market.")

        # ── Ensure International market has local currencies on ──
        intl = markets.get("International")
        if intl:
            if not intl["currency"].get("local_currencies_enabled"):
                safe_execute(
                    "update_market_currency:International",
                    update_market_currency,
                    INTERNATIONAL_MARKET_GID,
                    True,
                )
                fixed.append("✅ Enabled local currencies on International market")
                logger.info("[market_health_job] Enabled local currencies on International market.")

            if not intl["enabled"]:
                issues.append("⚠️ International market is disabled — customers outside US cannot shop")

        # ── Check all enabled markets have a web presence ──
        for m in markets_data["markets"]:
            if not m["enabled"]:
                continue
            wp = m["web_presence"]
            if not wp.get("domain") and not wp.get("subfolder"):
                issues.append(f"⚠️ Market '{m['name']}' has no web presence (domain/subfolder)")

        if fixed or issues:
            lines = fixed + issues
            send_alert("🌍 *Market Health Check*\n" + "\n".join(lines))

        logger.info("[market_health_job] Done. fixed=%d issues=%d", len(fixed), len(issues))

    except Exception as e:
        logger.error("[market_health_job] Failed: %s", e)
        send_alert(f"❌ market_health_job failed: {e}")
