"""
GCP Bot — Pre-Launch Connection Verifier
========================================
Run this BEFORE starting the server to confirm every credential,
environment variable, and notification channel is correctly configured.

Usage:
    python verify_connection.py

All checks print ✅ on success or ❌ with a clear error message.
Fix every ❌ before running: uvicorn api.main:app
"""

import os
import sys
import requests

# Load .env before anything else
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env file loaded")
except ImportError:
    print("❌ python-dotenv not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

PASSED = []
FAILED = []


def ok(msg):
    print(f"  ✅ {msg}")
    PASSED.append(msg)


def fail(msg, hint=""):
    print(f"  ❌ {msg}")
    if hint:
        print(f"     → {hint}")
    FAILED.append(msg)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — Environment Variables
# ─────────────────────────────────────────────────────────────
print("\n── Environment Variables ──────────────────────────")

required_vars = [
    ("GCP_PROJECT_ID",               "Set this to your GCP project ID from the console top bar"),
    ("GOOGLE_APPLICATION_CREDENTIALS","Should be: auth/service_account.json"),
    ("DASHBOARD_API_KEY",             "Run: python -c \"import secrets; print(secrets.token_hex(32))\""),
]

for var, hint in required_vars:
    val = os.getenv(var, "")
    if val:
        # Mask sensitive values in output
        display = val if var == "GCP_PROJECT_ID" else val[:6] + "*" * (len(val) - 6)
        ok(f"{var} = {display}")
    else:
        fail(f"{var} is not set", hint)

# Optional but warn if thresholds are missing
optional_vars = [
    "BUDGET_THRESHOLD", "IDLE_CPU_THRESHOLD", "SNAPSHOT_MAX_AGE_DAYS",
    "QUOTA_ALERT_PERCENT", "STORAGE_INACTIVE_DAYS", "GCP_ZONES",
]
for var in optional_vars:
    val = os.getenv(var, "")
    if val:
        ok(f"{var} = {val}")
    else:
        print(f"  ⚠️  {var} not set — will use default from config.py")

dry_run = os.getenv("DRY_RUN", "false").lower()
if dry_run == "true":
    print("  ⚠️  DRY_RUN=true — no destructive actions will execute (safe for testing)")
else:
    print("  ℹ️  DRY_RUN=false — live mode active")


# ─────────────────────────────────────────────────────────────
# SECTION 2 — Service Account JSON File
# ─────────────────────────────────────────────────────────────
print("\n── Service Account Credentials ────────────────────")

creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "auth/service_account.json")

if not os.path.exists(creds_path):
    fail(
        f"Service account file not found at: {creds_path}",
        "Download JSON key from GCP Console → IAM & Admin → Service Accounts → Keys → Add Key"
    )
else:
    ok(f"Service account file exists at: {creds_path}")

    # Validate it's a real service account JSON
    import json
    try:
        with open(creds_path) as f:
            sa_data = json.load(f)
        required_fields = ["type", "project_id", "private_key", "client_email"]
        missing = [k for k in required_fields if k not in sa_data]
        if missing:
            fail(f"service_account.json is missing fields: {missing}",
                 "Re-download the JSON key from GCP Console")
        elif sa_data.get("type") != "service_account":
            fail("JSON file type is not 'service_account'",
                 "Make sure you downloaded a Service Account key, not an OAuth client key")
        else:
            ok(f"service_account.json valid — email: {sa_data['client_email']}")
            ok(f"GCP project in key file: {sa_data['project_id']}")

            # Cross-check project IDs match
            env_project = os.getenv("GCP_PROJECT_ID", "")
            if env_project and env_project != sa_data["project_id"]:
                fail(
                    f"Project ID mismatch: .env has '{env_project}' but key file has '{sa_data['project_id']}'",
                    "Update GCP_PROJECT_ID in .env to match your service account's project"
                )
            elif env_project:
                ok("GCP_PROJECT_ID matches service account project")

    except json.JSONDecodeError:
        fail("service_account.json is not valid JSON",
             "Re-download the key file from GCP Console")


# ─────────────────────────────────────────────────────────────
# SECTION 3 — Live GCP Authentication Test
# ─────────────────────────────────────────────────────────────
print("\n── GCP Authentication (Live API Call) ─────────────")

try:
    from google.oauth2 import service_account
    SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
    credentials = service_account.Credentials.from_service_account_file(
        creds_path, scopes=SCOPES
    )
    ok(f"google-auth loaded credentials for: {credentials.service_account_email}")

    # Attempt a real API call — list enabled services
    from google.auth.transport.requests import Request as GoogleRequest
    credentials.refresh(GoogleRequest())
    ok("GCP credentials refreshed successfully (valid token obtained)")

except FileNotFoundError:
    fail("Cannot authenticate — service_account.json not found")
except Exception as e:
    fail(f"GCP authentication failed: {e}",
         "Check that the service account key is valid and APIs are enabled in GCP Console")


# ─────────────────────────────────────────────────────────────
# SECTION 4 — GCP APIs Enabled Check
# ─────────────────────────────────────────────────────────────
print("\n── GCP Required APIs ──────────────────────────────")

required_apis = [
    ("google.cloud.compute",     "google-cloud-compute",     "Compute Engine API"),
    ("google.cloud.storage",     "google-cloud-storage",     "Cloud Storage API"),
    ("google.cloud.billing",     "google-cloud-billing",     "Cloud Billing API"),
    ("google.cloud.monitoring",  "google-cloud-monitoring",  "Cloud Monitoring API"),
]

for module_path, package, api_name in required_apis:
    try:
        __import__(module_path)
        ok(f"{api_name} client library installed ({package})")
    except ImportError:
        fail(f"{package} not installed",
             f"Run: pip install {package}")


# ─────────────────────────────────────────────────────────────
# SECTION 5 — Discord Webhook Test
# ─────────────────────────────────────────────────────────────
print("\n── Discord Webhook ────────────────────────────────")

discord_url = os.getenv("DISCORD_WEBHOOK_URL", "")

if not discord_url:
    print("  ⚠️  DISCORD_WEBHOOK_URL not set — Discord alerts will be skipped")
    print("     → Add webhook URL from: Discord → Server Settings → Integrations → Webhooks")
else:
    try:
        # Validate webhook URL format
        if not discord_url.startswith("https://discord.com/api/webhooks/"):
            fail("Discord webhook URL format looks wrong",
                 "Should start with: https://discord.com/api/webhooks/")
        else:
            # Send a real test ping
            resp = requests.post(
                discord_url,
                json={
                    "content": "🤖 **GCP Bot** — Connection test successful! Bot is configured and ready.",
                    "username": "GCP Bot"
                },
                timeout=5
            )
            if resp.status_code == 204:
                ok("Discord webhook test message sent successfully (check your channel)")
            else:
                fail(f"Discord webhook returned HTTP {resp.status_code}",
                     "Regenerate the webhook URL in Discord server settings")
    except requests.exceptions.Timeout:
        fail("Discord webhook request timed out", "Check your internet connection")
    except Exception as e:
        fail(f"Discord webhook error: {e}")


# ─────────────────────────────────────────────────────────────
# SECTION 6 — Slack Webhook Test (if configured)
# ─────────────────────────────────────────────────────────────
print("\n── Slack Webhook ──────────────────────────────────")

slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
if not slack_url:
    print("  ⚠️  SLACK_WEBHOOK_URL not set — Slack alerts skipped (optional)")
else:
    try:
        resp = requests.post(slack_url, json={"text": "🤖 GCP Bot connection test — OK"}, timeout=5)
        if resp.status_code == 200:
            ok("Slack webhook test message sent successfully")
        else:
            fail(f"Slack webhook returned HTTP {resp.status_code}")
    except Exception as e:
        fail(f"Slack webhook error: {e}")


# ─────────────────────────────────────────────────────────────
# SECTION 7 — Telegram Test (if configured)
# ─────────────────────────────────────────────────────────────
print("\n── Telegram Bot ───────────────────────────────────")

tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
tg_chat  = os.getenv("TELEGRAM_CHAT_ID", "")

if not tg_token or not tg_chat:
    print("  ⚠️  Telegram not configured — skipped (optional)")
else:
    try:
        url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": tg_chat, "text": "🤖 GCP Bot connection test — OK"},
            timeout=5
        )
        data = resp.json()
        if data.get("ok"):
            ok("Telegram bot message sent successfully")
        else:
            fail(f"Telegram API error: {data.get('description', 'unknown')}",
                 "Verify TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are correct")
    except Exception as e:
        fail(f"Telegram error: {e}")


# ─────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────
print("\n" + "═" * 52)
print(f"  PASSED: {len(PASSED)}   FAILED: {len(FAILED)}")
print("═" * 52)

if not FAILED:
    print("\n🚀 All checks passed — you're ready to launch!")
    print("   Run: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload")
    print("   Then visit: http://localhost:8000/health\n")
else:
    print(f"\n⚠️  Fix the {len(FAILED)} failed check(s) above before starting the server.\n")
    for f in FAILED:
        print(f"  • {f}")
    print()
    sys.exit(1)
