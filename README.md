# The HUB — GCP Bot

Autonomous GCP management and e-commerce operations bot for **Legendary Branding**.
Deployed as a FastAPI service on Google Cloud Run (`gcp-bot`, region `us-central1`).

---

## Architecture

```
The_HUB/
├── api/                  # FastAPI app — entry point: api/main.py
│   ├── middleware/auth.py # X-API-Key guard
│   └── routers/          # One router per domain
├── agents/               # Multi-step orchestration agents
├── modules/              # Thin SDK wrappers (GCP + third-party)
├── scheduler/            # APScheduler background jobs
├── auth/credentials.py   # 3-layer credential resolution
├── config.py             # Env config, safe_execute(), retry_with_backoff()
├── cli.py                # Click CLI for manual operations
├── scripts/              # One-shot GitHub Actions workflow scripts
├── klaviyo_templates/    # Email template HTML + build pipeline
└── razorpay-backend/     # Separate Cloud Run service (Razorpay payments)
```

### Layering convention

| Layer | Location | Rule |
|---|---|---|
| SDK wrappers | `modules/` | Never import from `api/` or `agents/` |
| HTTP routes | `api/routers/` | Call `modules/` only; protected by `X-API-Key` |
| Orchestration | `agents/` | May call multiple modules; use `safe_execute()` |

---

## Modules

| Module | Description |
|---|---|
| `modules/shopify.py` | Shopify Admin REST + GraphQL v2026-04 |
| `modules/klaviyo.py` | Klaviyo email API |
| `modules/gemini.py` | Google Gemini / Vertex AI |
| `modules/sheets.py` | Google Sheets read/write |
| `modules/indexing.py` | Google Search Indexing API |
| `modules/tag_manager.py` | Google Tag Manager |
| `modules/storage.py` | Google Cloud Storage |
| `modules/compute.py` | Compute Engine (VMs, snapshots) |
| `modules/billing.py` | Cloud Billing + Budget alerts |
| `modules/monitoring.py` | Cloud Monitoring metrics |
| `modules/cloud_logging.py` | Cloud Logging |
| `modules/secret_manager.py` | Secret Manager CRUD |
| `modules/higgsfield.py` | Higgsfield AI video generation |
| `modules/nvidia_vision.py` | NVIDIA vision/image AI |

---

## Scheduler jobs

All jobs run as APScheduler background threads inside the Cloud Run container (timezone: `America/Chicago`).

| Job ID | Schedule | Description |
|---|---|---|
| `daily_cost_check` | Daily 08:00 | Billing alert |
| `weekly_snapshot_cleanup` | Monday 09:00 | Delete snapshots >30 days |
| `vm_health_pulse` | Every 15 min | VM health check |
| `nightly_idle_shutdown` | Daily 00:00 | Stop idle VMs |
| `monthly_report` | 1st of month 07:00 | Monthly GCP usage report |
| `weekly_storage_audit` | Sunday 06:00 | Storage bucket audit |
| `quota_check` | Every 6 hours | Quota usage check (alert at 80%) |
| `daily_indexing_submission` | Daily 06:00 | Submit sitemap URLs to Indexing API |
| `daily_sheets_refresh` | Daily 07:00 | Refresh Google Sheets dashboard |
| `error_log_monitor` | Every 6 hours | Monitor Cloud Run error logs |
| `indexnow_new_products` | Daily 06:15 | Ping IndexNow for products published in last 24h |
| `alt_text_auto_patch` | Daily 06:30 | Auto-fill missing product image alt text |
| `shopify_product_health` | Daily 09:00 | Audit SKU/barcode/product-type coverage; alert on gaps |
| `gmc_disapproval_check` | Daily 10:00 | Alert on GMC disapprovals and critical data quality issues |
| `gmc_shipping_drift_check` | Wednesday 08:00 | Alert when Shopify and GMC shipping configs diverge |
| `klaviyo_flow_health` | Tuesday 08:00 | Alert if any critical email flow is paused or missing a template |
| `gmc_title_rotation` | Wednesday 10:00 | CTR-based A/B title rotation for GMC free listings; saves state to GCS |

Control jobs at runtime:

```
GET  /api/scheduler/jobs
POST /api/scheduler/jobs/{job_id}/pause
POST /api/scheduler/jobs/{job_id}/resume
POST /api/scheduler/jobs/{job_id}/run
```

---

## Setup

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
# Create .env and fill in values (see Environment Variables below)
cp .env.example .env
```

Set `DRY_RUN=true` in `.env` to prevent real GCP mutations during development.

### 3. Run locally

```bash
# API server
uvicorn api.main:app --reload --port 8080

# CLI
python cli.py list-vms --zone us-central1-a

# Scheduler standalone
python scheduler/jobs.py
```

---

## CLI reference

```bash
# Theme deployment
python cli.py deploy --dir ./my-theme --label "summer-drop-v2"
python cli.py versions
python cli.py rollback --version 20240517T120000Z
python cli.py push-shopify --dir ./my-theme --theme-id 123456789

# VM management
python cli.py list-vms --zone us-central1-a
python cli.py list-all-vms
python cli.py start-vm   --zone us-central1-a --name my-vm
python cli.py stop-vm    --zone us-central1-a --name my-vm
python cli.py delete-vm  --zone us-central1-a --name my-vm --confirm
python cli.py auto-stop-idle --zone us-central1-a --cpu 5.0

# Billing
python cli.py billing-info
python cli.py budget-check
python cli.py spend --dataset billing_export --table gcp_billing_export_v1_XXXX --days 30
```

---

## API

All routes require `X-API-Key: <DASHBOARD_API_KEY>` except `GET /health`.

| Prefix | Domain |
|---|---|
| `/api/compute` | Compute Engine |
| `/api/storage` | Cloud Storage |
| `/api/billing` | Billing |
| `/api/monitoring` | Cloud Monitoring |
| `/api/shopify` | Shopify |
| `/api/klaviyo` | Klaviyo |
| `/api/gemini` | Gemini AI |
| `/api/sheets` | Google Sheets |
| `/api/indexing` | Search Indexing |
| `/api/gtm` | Google Tag Manager |
| `/api/secrets` | Secret Manager |
| `/api/logs` | Cloud Logging |
| `/api/higgsfield` | Higgsfield AI |
| `/api/seo` | SEO utilities |
| `/api/analytics` | Google Analytics |
| `/api/pagespeed` | PageSpeed Insights |
| `/api/scheduler` | Scheduler control |
| `/health` | Health check (unauthenticated) |
| `/webhooks` | Shopify webhook receiver (HMAC-verified, no API key) |

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GCP_PROJECT_ID` | — | GCP project ID |
| `DASHBOARD_API_KEY` | — | API key for all protected routes |
| `DRY_RUN` | `false` | Set `true` to disable all destructive actions |
| `GCP_SA_KEY_JSON` | — | Raw JSON service account key |
| `GCP_ZONES` | `us-central1-a,us-central1-b` | Compute zones |
| `BUDGET_THRESHOLD` | `100` | Billing alert threshold (USD) |
| `IDLE_CPU_THRESHOLD` | `2.0` | CPU % threshold for idle VM detection |
| `QUOTA_ALERT_PERCENT` | `80` | Quota usage % to trigger alert |
| `SNAPSHOT_MAX_AGE_DAYS` | `30` | Max snapshot age before cleanup |
| `SHOPIFY_STORE_DOMAIN` | `lngndny.myshopify.com` | Shopify store domain |
| `SHOPIFY_CLIENT_ID` | — | Shopify OAuth client ID |
| `SHOPIFY_CLIENT_SECRET` | — | Shopify OAuth client secret |
| `SHOPIFY_ADMIN_TOKEN` | — | Bootstrap token (auto-refreshed via OAuth) |
| `KLAVIYO_API_KEY` | — | Klaviyo private API key |
| `GOOGLE_API_KEY` | — | Google API key (PageSpeed, etc.) |
| `GA4_PROPERTY_ID` | — | Google Analytics 4 property |
| `PAGESPEED_URL` | — | Target URL for PageSpeed audits |
| `PAGESPEED_API_KEY` | — | PageSpeed Insights API key |
| `HIGGSFIELD_API_KEY_ID` | — | Higgsfield AI key ID |
| `HIGGSFIELD_API_KEY_SECRET` | — | Higgsfield AI key secret |
| `NVIDIA_API_KEY` | — | NVIDIA API key |
| `GSC_TOKEN_JSON` | — | Google Search Console OAuth token JSON |
| `GMC_MERCHANT_ID` | — | Google Merchant Center account/merchant ID |
| `INDEXNOW_API_KEY` | — | IndexNow API key for search engine pings |
| `SITE_DOMAIN` | `legendary-branding.com` | Public storefront domain |
| `SHOPIFY_WEBHOOK_SECRET` | — | Secret for verifying Shopify HMAC webhook signatures |

---

## CI/CD

Deploys to Cloud Run on push to `main` via `.github/workflows/deploy.yml`.

**Pipeline:**
1. Lint (`flake8`, max line 120, fatal on `E9,F63,F7,F82`) + `pytest` if tests exist
2. Build Docker image → `gcr.io/<PROJECT>/gcp-bot:<sha>`
3. Deploy scalar env vars via `gcloud run deploy --clear-secrets`
4. Inject `GCP_SA_KEY_JSON` + `GSC_TOKEN_JSON` as plain env vars via `gcloud run services replace`
5. Health check `GET /health`

**Required GitHub secrets:** `GCP_SA_KEY`, `GCP_PROJECT_ID`, `DASHBOARD_API_KEY`, `GA4_PROPERTY_ID`, `GOOGLE_API_KEY`, `BUDGET_THRESHOLD`, `IDLE_CPU_THRESHOLD`, `QUOTA_ALERT_PERCENT`, `PAGESPEED_URL`, `PAGESPEED_API_KEY`, `HIGGSFIELD_API_KEY_ID`, `HIGGSFIELD_API_KEY_SECRET`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `SHOPIFY_ADMIN_TOKEN`, `KLAVIYO_API_KEY`, `NVIDIA_API_KEY`, `GSC_TOKEN_JSON`

---

## IAM roles

| Module / Agent | Required Role |
|---|---|
| Storage | `roles/storage.objectAdmin` |
| Compute | `roles/compute.instanceAdmin.v1`, `roles/compute.viewer` |
| Billing | `roles/billing.viewer` |
| Billing (BigQuery) | `roles/bigquery.dataViewer` |
| Monitoring | `roles/monitoring.viewer` |
| Cloud Logging | `roles/logging.viewer` |
| Secret Manager | `roles/secretmanager.secretAccessor` |
| Google Tag Manager | GTM account-level read/edit/publish |
| Indexing API | Delegated SA on Google Search Console property |

---

## Security

- **Never commit** `auth/service_account.json`, `.env`, or any credential file
- All routes except `GET /health` require `X-API-Key`
- Destructive CLI commands require `--confirm`
- Use `DRY_RUN=true` in development — all destructive actions are no-ops
- Credentials resolved in priority order: `GCP_SA_KEY_JSON` env var → `GOOGLE_APPLICATION_CREDENTIALS` file → Application Default Credentials
