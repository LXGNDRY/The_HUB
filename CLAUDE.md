# CLAUDE.md — The HUB (GCP Bot)

Autonomous GCP management and e-commerce operations bot for **Legendary Branding**.
Deployed as a FastAPI service on Google Cloud Run (`gcp-bot`, region `us-central1`).

---

## Repository layout

```
The_HUB/
├── api/                  # FastAPI app — entry point: api/main.py
│   ├── middleware/auth.py # X-API-Key guard (DASHBOARD_API_KEY)
│   └── routers/          # One router per domain (compute, shopify, klaviyo, …)
├── agents/               # Higher-level automation agents
├── modules/              # Low-level GCP/third-party SDK wrappers
├── scheduler/
│   ├── engine.py         # BotScheduler (APScheduler BackgroundScheduler)
│   └── jobs.py           # Job functions registered in engine.py
├── auth/credentials.py   # 3-layer credential resolution (see below)
├── config.py             # Env-var config + safe_execute() + retry_with_backoff()
├── cli.py                # Click CLI for manual operations
├── scripts/              # One-shot workflow scripts (run via GitHub Actions)
├── klaviyo_templates/    # Email template HTML + build scripts
├── razorpay-backend/     # Separate Cloud Run service for Razorpay payments
├── reports/              # Output directory for exported CSVs (gitignored except .gitkeep)
├── Dockerfile            # Container image for gcp-bot service
├── cloudrun.yaml         # Cloud Run service spec template
├── deploy.sh             # Manual deploy helper
└── .github/workflows/    # CI/CD + operational automation workflows
```

---

## Architecture patterns

### Module → Router → Agent layering

- **`modules/`** — thin SDK wrappers around a single GCP service or third-party API.
  Each module exposes plain Python functions; it never imports from `api/` or `agents/`.
- **`api/routers/`** — FastAPI routers that call into `modules/`. One router per domain,
  registered in `api/main.py` under `/api/<domain>`. All protected routes require
  `X-API-Key`; webhook, OAuth, and dashboard routes are unauthenticated.
- **`agents/`** — orchestration logic that may call multiple modules, run multi-step
  workflows, and use `config.safe_execute()` for destructive actions.
  - `agents/blog_writer_agent.py` — Gemini-powered blog generation; runs via scheduler 3×/day and `POST /api/blog-writer/run`
  - `agents/vision_agent.py` — NVIDIA NIM vision; alt text audit/apply and product description gen via `POST /api/vision/*`

### `config.py` utilities — use these everywhere

```python
from config import safe_execute, retry_with_backoff, DRY_RUN

# Gate any destructive action behind DRY_RUN
safe_execute("delete_object:my-key", storage_client.delete, bucket, key)

# Retry GCP API calls with exponential backoff
@retry_with_backoff(max_attempts=3, base_delay=1.0)
def call_gcp(): ...
```

`DRY_RUN=true` in env prevents all destructive actions and logs what would have run.
**Always use `safe_execute()` for deletes, stops, mutations.**

### Authentication (`auth/credentials.py`)

Three fallback layers — highest priority wins:
1. `GCP_SA_KEY_JSON` env var — raw JSON string of a service account key
2. `GOOGLE_APPLICATION_CREDENTIALS` — path to a key file
3. Application Default Credentials (Cloud Run metadata server)

Never commit `auth/service_account.json` or `.env`. In production, credentials arrive
as env vars injected by the CI deploy pipeline.

---

## API conventions

- **Base prefix**: `/api/<domain>` (e.g. `/api/shopify`, `/api/compute`)
- **Auth header**: `X-API-Key: <DASHBOARD_API_KEY>` on every request
- **Health check**: `GET /health` — unauthenticated, returns scheduler job count
- **Shopify API version**: `2026-04` (REST + GraphQL)
- **Scheduler timezone**: `America/Chicago`
- **Embedded dashboard**: `GET /app` — unauthenticated, serves `frontend/index.html` (Shopify App Bridge UI)
- **Shopify OAuth**: `GET /auth/shopify` + `GET /auth/shopify/callback` — unauthenticated, handles install/callback
- **Webhooks**: `POST /webhooks/shopify` — unauthenticated, HMAC-verified via `SHOPIFY_WEBHOOK_SECRET`
- **Static assets**: `GET /frontend/*` — served from `frontend/` directory

All protected routers use `**protected` shorthand defined in `api/main.py`:
```python
protected = {"dependencies": [Depends(verify_api_key)]}
app.include_router(router, prefix="/api/foo", tags=["Foo"], **protected)
```

Routers mounted **without** `**protected` (no X-API-Key required):
- `webhooks.router` at `/webhooks` — Shopify HMAC signature is the auth mechanism
- `oauth.router` — install/callback redirect flow
- `app_dashboard.router` — serves the embedded UI at `/app`

---

## Scheduler jobs

Registered in `scheduler/engine.py`, functions live in `scheduler/jobs.py`.
APScheduler runs as a background thread in the same Cloud Run container.

| Job ID | Schedule | Description |
|---|---|---|
| `daily_cost_check` | Daily 08:00 CT | Billing alert |
| `weekly_snapshot_cleanup` | Monday 09:00 CT | Delete snapshots >30 days |
| `vm_health_pulse` | Every 15 min | VM health check |
| `nightly_idle_shutdown` | Daily 00:00 CT | Stop idle VMs (<CPU threshold) |
| `monthly_report` | 1st of month 07:00 CT | Monthly GCP usage report |
| `weekly_storage_audit` | Sunday 06:00 CT | Storage bucket audit |
| `quota_check` | Every 6 hours | Quota usage check (alert at 80%) |
| `daily_indexing_submission` | Daily 06:00 CT | Submit sitemap URLs to Indexing API |
| `daily_sheets_refresh` | Daily 07:00 CT | Refresh Google Sheets dashboard |
| `error_log_monitor` | Every 6 hours | Monitor Cloud Run error logs |
| `indexnow_new_products` | Daily 06:15 CT | Ping IndexNow for products published in last 24h |
| `alt_text_auto_patch` | Daily 06:30 CT | Auto-fill missing image alt text (idempotent) |
| `shopify_product_health` | Daily 09:00 CT | Audit product SKU/barcode/type coverage; alert on gaps |
| `gmc_disapproval_check` | Daily 10:00 CT | Alert on GMC disapprovals and critical data quality issues |
| `gmc_shipping_drift_check` | Wednesday 08:00 CT | Alert when Shopify and GMC shipping are out of sync |
| `klaviyo_flow_health` | Tuesday 08:00 CT | Alert if any of the 7 critical email flows are paused or missing a template |
| `gmc_title_rotation` | Wednesday 10:00 CT | CTR-based A/B title rotation for GMC free listings; saves rotation state to GCS |
| `blog_writer_morning` | Daily 08:00 CT | Generate + publish one SEO blog post to Shopify |
| `blog_writer_midday` | Daily 12:00 CT | Generate + publish one SEO blog post to Shopify |
| `blog_writer_afternoon` | Daily 16:00 CT | Generate + publish one SEO blog post to Shopify |
| `nightly_compliance_patch` | Daily 02:00 CT | Fill missing COO + HS code on all variants (idempotent) |
| `nightly_product_type_patch` | Daily 02:30 CT | Standardize product_type to Google Shopping taxonomy (idempotent) |
| `nightly_product_weight_patch` | Daily 02:45 CT | Fill missing variant weights from taxonomy defaults (idempotent) |
| `market_health_check` | Daily 06:45 CT | Ensure international markets stay enabled + local currencies active |
| `gmc_auto_fix` | Daily 11:00 CT | Auto-fix GMC disapprovals (patch brand + identifierExists) + apply apparel attribute rules to all feeds |
| `gmc_shipping_sync` | Wednesday 08:30 CT | Auto-sync Shopify shipping zones → GMC (add missing countries); runs after shipping drift check |

Compute-dependent jobs (`vm_health_pulse`, `nightly_idle_shutdown`, `weekly_snapshot_cleanup`)
self-check API availability at runtime and skip gracefully — do not remove them if Compute
Engine API is temporarily unavailable.

Scheduler can be controlled at runtime via:
- `GET /api/scheduler/jobs` — list all jobs and next run times
- `POST /api/scheduler/jobs/{job_id}/pause`
- `POST /api/scheduler/jobs/{job_id}/resume`
- `POST /api/scheduler/jobs/{job_id}/run` — trigger immediately

---

## Modules reference

| Module | Description |
|---|---|
| `modules/shopify.py` | Shopify Admin REST + GraphQL (products, orders, shipping, themes, …) |
| `modules/klaviyo.py` | Klaviyo email API (flows, templates, metrics) |
| `modules/gemini.py` | Google Gemini / Vertex AI generative AI calls |
| `modules/sheets.py` | Google Sheets read/write |
| `modules/indexing.py` | Google Search Indexing API |
| `modules/tag_manager.py` | Google Tag Manager |
| `modules/storage.py` | Google Cloud Storage |
| `modules/compute.py` | Compute Engine (VMs, snapshots) |
| `modules/billing.py` | Cloud Billing + Budget alerts |
| `modules/monitoring.py` | Cloud Monitoring metrics |
| `modules/cloud_logging.py` | Cloud Logging read/write |
| `modules/secret_manager.py` | Secret Manager CRUD |
| `modules/higgsfield.py` | Higgsfield AI video generation |
| `modules/nvidia_vision.py` | NVIDIA vision/image AI |

### Shopify token management

`modules/shopify.py` uses a module-level `_TokenCache` singleton. Tokens are
auto-refreshed when within 5 minutes of expiry. `SHOPIFY_ADMIN_TOKEN` bootstraps
the cache on startup; thereafter `SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET` are
used for OAuth Client Credentials refreshes. Do not directly read the token — always
call the module's internal `_ensure_token()` before making requests.

---

## Scripts (`scripts/`)

One-shot Python scripts triggered by GitHub Actions workflows. Each script is
independently runnable and should be idempotent where possible. Common patterns:

- Scripts accept configuration via env vars (same vars as the API service)
- Scripts use `modules/` for all API calls — do not duplicate SDK logic
- GMC (Google Merchant Center) scripts are prefixed `gmc_`
- Shopify scripts are prefixed with their function (e.g. `audit_shipping.py`, `fix_shopify_product_data.py`)

---

## Klaviyo templates (`klaviyo_templates/`)

HTML email templates for Legendary Branding. Build flow:

```bash
python klaviyo_templates/build_templates.py
# Output written to klaviyo_templates/output/
```

Template IDs are stored in `klaviyo_templates/v2_template_ids.json`.
See `klaviyo_templates/README.md` for full build and deploy instructions.

---

## Razorpay backend (`razorpay-backend/`)

Separate Cloud Run service (`lb-razorpay-backend`, project `idx-lngndny`).
Deployed via Cloud Build (`razorpay-backend/cloudbuild.yaml`), not the main
GitHub Actions pipeline. Secrets are injected via Secret Manager at deploy time.

---

## Environment variables

| Variable | Description |
|---|---|
| `GCP_PROJECT_ID` | GCP project ID |
| `DASHBOARD_API_KEY` | API key for all protected routes |
| `DRY_RUN` | `true` to disable destructive actions |
| `GCP_SA_KEY_JSON` | Raw JSON service account key |
| `GA4_PROPERTY_ID` | Google Analytics 4 property |
| `GOOGLE_API_KEY` | Google API key (PageSpeed, etc.) |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Google Ads API developer token |
| `GOOGLE_ADS_CLIENT_ID` | Google Ads OAuth client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | Google Ads OAuth client secret |
| `GOOGLE_ADS_REFRESH_TOKEN` | Google Ads OAuth refresh token |
| `BUDGET_THRESHOLD` | Billing alert threshold (USD, default 100) |
| `IDLE_CPU_THRESHOLD` | CPU % below which a VM is considered idle (default 2.0) |
| `QUOTA_ALERT_PERCENT` | Quota usage % to trigger alert (default 80) |
| `SNAPSHOT_MAX_AGE_DAYS` | Max snapshot age before cleanup (default 30) |
| `PAGESPEED_URL` | Target URL for PageSpeed audits |
| `PAGESPEED_API_KEY` | Google PageSpeed Insights API key |
| `SHOPIFY_STORE_DOMAIN` | `lngndny.myshopify.com` |
| `SHOPIFY_CLIENT_ID` | Shopify OAuth client ID |
| `SHOPIFY_CLIENT_SECRET` | Shopify OAuth client secret |
| `SHOPIFY_ADMIN_TOKEN` | Shopify Admin API bootstrap token |
| `KLAVIYO_API_KEY` | Klaviyo private API key |
| `HIGGSFIELD_API_KEY_ID` | Higgsfield AI key ID |
| `HIGGSFIELD_API_KEY_SECRET` | Higgsfield AI key secret |
| `NVIDIA_API_KEY` | NVIDIA API key |
| `GSC_TOKEN_JSON` | Google Search Console OAuth token JSON |
| `GMC_MERCHANT_ID` | Google Merchant Center account/merchant ID |
| `INDEXNOW_API_KEY` | IndexNow API key for real-time search engine URL pings |
| `SITE_DOMAIN` | Public storefront domain (default `legendary-branding.com`) |
| `SHOPIFY_WEBHOOK_SECRET` | Secret for verifying Shopify HMAC webhook signatures |
| `BLOG_SHOPIFY_BLOG_ID` | Shopify blog ID to publish articles to (auto-detected if unset) |
| `BLOG_POSTS_PER_RUN` | Number of posts per scheduler run (default `1`) |
| `BLOG_AUTHOR` | Author name on published articles (default `Legendary Branding`) |
| `GCP_ZONES` | Comma-separated Compute zones (default `us-central1-a,us-central1-b`) |
| `GMC_MERCHANT_ID` | Google Merchant Center account/merchant ID |
| `INDEXNOW_API_KEY` | IndexNow API key for real-time search engine pings |
| `SITE_DOMAIN` | Public storefront domain (default `legendary-branding.com`) |

### Google Ads connection

Used via the `google-ads` Python SDK (`GoogleAdsClient`), authenticated with the
four `GOOGLE_ADS_*` secrets above. Ads account (`login_customer_id`) is hardcoded
per-script as `CUSTOMER_ID` (currently `1137623123`) rather than read from an env
var. Used by:

| Script | Workflow | Purpose |
|---|---|---|
| `scripts/pmax_report.py` | `pmax-report.yml` | Performance Max campaign reporting (scheduled) |
| `scripts/pmax_campaign_setup.py`, `scripts/pmax_rest_setup.py` | `pmax-campaign-setup.yml` | Set up PMax campaigns |
| `scripts/pmax_geo_expand.py` | `pmax-geo-expand.yml` | Geo-targeting expansion |
| `scripts/pmax_exclude_placements.py` | `pmax-exclude-placements.yml` | Placement exclusions |
| `scripts/check_asset_groups.py` | `check-asset-groups.yml` | Asset group audit |
| `scripts/google_ads_checkout_audit.py` | `google-ads-checkout-audit.yml` | Checkout/conversion audit |
| `scripts/gtm_purchase_fix.py` | `gtm-purchase-fix.yml` | GTM purchase-tracking fix (touches Ads conversion tags) |

---

## CI/CD (`.github/workflows/deploy.yml`)

Triggers on push to `main` or manual `workflow_dispatch`.

**Pipeline jobs:**
1. **Lint & Test** — `flake8` (errors-only + style), `pytest tests/` if tests exist
2. **Build & Push** — Docker image tagged `gcr.io/<PROJECT>/gcp-bot:<sha>` and `:latest`
3. **Deploy** — Two-step Cloud Run deploy:
   - Step 1: `gcloud run deploy` with all scalar env vars + `--clear-secrets`
   - Step 2: Python script patches YAML spec to inject `GCP_SA_KEY_JSON` and `GSC_TOKEN_JSON` as plain env var values (these are JSON blobs, not Secret Manager refs)
4. **IAM binding** — Sets `allUsers` as invoker (non-fatal if SA lacks `roles/run.admin`)
5. **Health check** — Polls `/health` up to 5 times

**Required GitHub secrets:**
`GCP_SA_KEY`, `GCP_PROJECT_ID`, `DASHBOARD_API_KEY`, `GA4_PROPERTY_ID`,
`GOOGLE_API_KEY`, `BUDGET_THRESHOLD`, `IDLE_CPU_THRESHOLD`, `QUOTA_ALERT_PERCENT`,
`PAGESPEED_URL`, `PAGESPEED_API_KEY`, `HIGGSFIELD_API_KEY_ID`, `HIGGSFIELD_API_KEY_SECRET`,
`SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `SHOPIFY_ADMIN_TOKEN`,
`KLAVIYO_API_KEY`, `NVIDIA_API_KEY`, `GSC_TOKEN_JSON`

**Additional secrets used by Google Ads workflows** (not part of the main
`deploy.yml` pipeline, but required by the workflows listed under
[Google Ads connection](#google-ads-connection)):
`GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`,
`GOOGLE_ADS_REFRESH_TOKEN`

**Lint rules:** `flake8` max line length 120, max complexity 10. Fatal on `E9,F63,F7,F82` only.

---

## Local development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and fill in env vars
cp .env.example .env   # (if .env.example exists, else create .env manually)

# Run the API server
uvicorn api.main:app --reload --port 8080

# Run a CLI command
python cli.py list-vms --zone us-central1-a

# Run the scheduler standalone
python scheduler/jobs.py
```

Set `DRY_RUN=true` in `.env` when developing to prevent real GCP mutations.

---

## Adding new functionality

### New module
1. Create `modules/<service>.py` — wrap the SDK, expose plain functions, use `logger = logging.getLogger("gcp-bot.<service>")`
2. Use `@retry_with_backoff()` on network calls
3. Gate destructive calls with `safe_execute()`

### New API route
1. Create `api/routers/<service>.py` with a `router = APIRouter()`
2. Import and mount in `api/main.py` with the `**protected` dict

### New scheduler job
1. Add the job function to `scheduler/jobs.py`
2. Import it in `scheduler/engine.py` and register with `self.scheduler.add_job()`

### New script
1. Add `scripts/<task>.py` — standalone, reads env vars, uses `modules/`
2. Add a corresponding `workflows/<task>.yml` if it should be triggerable from GitHub

---

## Security rules

- **Never commit** `auth/service_account.json`, `.env`, or any file containing credentials
- Service account follows least-privilege — only roles the specific agent needs
- `delete-vm` and other destructive CLI commands require explicit `--confirm` flag
- CORS is currently `allow_origins=["*"]` — restrict to your dashboard origin in production
- All routes except `GET /health` are protected by `X-API-Key`
- Use `DRY_RUN=true` in staging/development environments

---

## IAM roles summary

| Module / Agent | Required GCP Role |
|---|---|
| Storage (themes) | `roles/storage.objectAdmin` |
| Compute | `roles/compute.instanceAdmin.v1`, `roles/compute.viewer` |
| Billing | `roles/billing.viewer` |
| Billing (BigQuery export) | `roles/bigquery.dataViewer` |
| Monitoring (idle VM check) | `roles/monitoring.viewer` |
| Cloud Logging | `roles/logging.viewer` |
| Secret Manager | `roles/secretmanager.secretAccessor` |
| Google Tag Manager | GTM account-level read/edit/publish |
| Indexing API | Owner/delegated SA on Google Search Console property |
