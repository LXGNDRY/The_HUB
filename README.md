# GCP Bot

Custom Google Cloud Platform automation bot for **Legendary Branding**.
Built in Python using official Google Cloud client libraries.

---

## Agents

| Agent | File | Status |
|---|---|---|
| Theme Deployment | `agents/theme_deployment_agent.py` | ✅ Live |
| Compute Manager | `agents/compute_agent.py` | 🔜 Next |
| Storage Agent | `agents/storage_agent.py` | 🔜 Planned |
| Billing Monitor | `agents/billing_agent.py` | 🔜 Planned |
| Scheduler | `scheduler/jobs.py` | 🔜 Planned |

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
- Create a **Service Account** in GCP IAM with `roles/storage.objectAdmin`
- Download the JSON key → save to `auth/service_account.json`
- `auth/service_account.json` is gitignored — never commit it

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env with your GCP project ID, bucket name, Shopify credentials
```

### 4. Create your GCS theme bucket
```bash
gcloud storage buckets create gs://legendary-branding-themes --location=us-central1
```

---

## Theme Deployment Agent

Automates theme versioning, rollback, and deployment between your local machine,
Google Cloud Storage, and Shopify.

### CLI Commands

```bash
# Deploy theme to GCS (creates versioned snapshot + updates live/)
python cli.py deploy --dir ./my-theme --label "summer-drop-v2"

# List recent versions
python cli.py versions

# Rollback live snapshot to a previous version
python cli.py rollback --version 20240517T120000Z

# Download current live theme from GCS
python cli.py download --dest ./downloaded-theme

# Push directly to Shopify via Admin API
python cli.py push-shopify --dir ./my-theme --theme-id 123456789

# Diff two versions
python cli.py diff --a 20240517T120000Z --b 20240518T090000Z
```

---

## GCS Bucket Structure

```
gs://legendary-branding-themes/
    live/                          ← current live snapshot
        assets/
        config/
        layout/
        ...
    versions/
        20240517T120000Z/          ← timestamped archive
            assets/
            meta.json              ← version metadata
        20240518T090000Z/
            ...
```

---

## Security Notes

- **Never commit** `auth/service_account.json` or `.env`
- Service account should have **minimum required roles** only
- Enable **Cloud Audit Logs** in GCP for all API calls
- Use **Workload Identity Federation** in production instead of JSON keys

---

## Roadmap

- [ ] Compute agent (start/stop/list VMs)
- [ ] Billing monitor with Slack alerts
- [ ] Scheduler for automated nightly backups
- [ ] Discord bot interface
- [ ] Web dashboard (FastAPI + custom UI)
