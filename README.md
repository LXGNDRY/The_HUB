# GCP Bot

Custom Google Cloud Platform automation bot for **Legendary Branding**.
Built in Python using official Google Cloud client libraries.

---

## Agents

| Agent | File | Status |
|---|---|---|
| Theme Deployment | `agents/theme_deployment_agent.py` | ✅ Live |
| Compute Manager | `agents/compute_agent.py` | ✅ Live |
| Billing Monitor | `agents/billing_agent.py` | ✅ Live |
| Scheduler | `scheduler/jobs.py` | ✅ Live |
| Storage Agent | `agents/storage_agent.py` | 🔜 Next |
| BigQuery Agent | `agents/bigquery_agent.py` | 🔜 Planned |
| Discord Bot Interface | `interfaces/discord_bot.py` | 🔜 Planned |
| Web Dashboard | `interfaces/dashboard/` | 🔜 Planned |

---

## Setup

### 1. Clone & install dependencies
```bash
git clone https://github.com/LXGNDRY/gcp-bot.git
cd gcp-bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Add credentials
- Create a **Service Account** in GCP IAM with the required roles (see each agent's docstring)
- Download the JSON key → save to `auth/service_account.json`
- `auth/service_account.json` is gitignored — never commit it

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env with your GCP project ID, bucket, billing account, Shopify credentials
```

### 4. Create your GCS theme bucket (one-time)
```bash
gcloud storage buckets create gs://legendary-branding-themes --location=us-central1
```

---

## Theme Deployment Agent

```bash
# Deploy theme to GCS
python cli.py deploy --dir ./my-theme --label "summer-drop-v2"

# List versions
python cli.py versions

# Rollback
python cli.py rollback --version 20240517T120000Z

# Download live snapshot
python cli.py download --dest ./downloaded-theme

# Push to Shopify directly
python cli.py push-shopify --dir ./my-theme --theme-id 123456789

# Diff two versions
python cli.py diff --a 20240517T120000Z --b 20240518T090000Z
```

---

## Compute Agent

Required IAM: `roles/compute.instanceAdmin.v1`, `roles/compute.viewer`

```bash
# List VMs
python cli.py list-vms --zone us-central1-a
python cli.py list-all-vms

# Control VMs
python cli.py start-vm   --zone us-central1-a --name my-vm
python cli.py stop-vm    --zone us-central1-a --name my-vm
python cli.py restart-vm --zone us-central1-a --name my-vm
python cli.py delete-vm  --zone us-central1-a --name my-vm --confirm

# Create a VM
python cli.py create-vm --zone us-central1-a --name dev-server --machine e2-micro --disk 20

# Snapshots
python cli.py list-snapshots
python cli.py cleanup-snapshots --days 30 --dry-run

# Auto-stop idle VMs (avg CPU < 5% over last hour)
python cli.py auto-stop-idle --zone us-central1-a --cpu 5.0
```

---

## Billing Agent

Required IAM: `roles/billing.viewer`  
For BQ spend queries: enable [Billing Export to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery) in GCP Console.

```bash
# Project billing info
python cli.py billing-info

# List budgets
python cli.py budgets

# Check budget vs threshold
python cli.py budget-check

# Spend report by service (requires BQ export)
python cli.py spend --dataset billing_export --table gcp_billing_export_v1_XXXX --days 30 --export reports/spend.csv

# Detect cost spikes >20% day-over-day
python cli.py spikes --dataset billing_export --table gcp_billing_export_v1_XXXX

# Full daily check (runs all of the above)
python cli.py billing-check --dataset billing_export --table gcp_billing_export_v1_XXXX
```

---

## Scheduler

Runs automated jobs continuously. Keep alive on a VM, or deploy to Cloud Run Jobs.

```bash
python scheduler/jobs.py
```

| Job | Schedule |
|---|---|
| Billing daily check | Every day @ 08:00 |
| Snapshot cleanup (>30 days) | Every Monday @ 09:00 |
| Idle VM auto-stop (<5% CPU) | Every day @ 23:00 |

---

## GCS Bucket Structure

```
gs://legendary-branding-themes/
    live/                          ← current live snapshot
    versions/
        20240517T120000Z/
            assets/
            meta.json
        20240518T090000Z/
            ...
```

---

## Required IAM Roles Summary

| Agent | Required Role |
|---|---|
| Theme Deployment | `roles/storage.objectAdmin` |
| Compute Agent | `roles/compute.instanceAdmin.v1`, `roles/compute.viewer` |
| Billing Agent | `roles/billing.viewer` |
| Billing (BQ) | `roles/bigquery.dataViewer` |
| Auto-stop idle VMs | `roles/monitoring.viewer` |

---

## Security Notes

- **Never commit** `auth/service_account.json` or `.env`
- Service account should have **minimum required roles** only
- Enable **Cloud Audit Logs** in GCP for full API call history
- Use **Workload Identity Federation** in production instead of JSON keys
- `delete-vm` requires explicit `--confirm` flag — no accidental deletions

---

## Roadmap

- [ ] Storage agent (bucket CRUD, file sync)
- [ ] BigQuery agent (dataset management, query runner)
- [ ] Discord bot interface (control bot from phone)
- [ ] Web dashboard (FastAPI + custom UI)
- [ ] Shopify ↔ BigQuery order sync
