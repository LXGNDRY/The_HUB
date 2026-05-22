#!/usr/bin/env python3
"""
pull_error_logs.py
Pulls recent error logs from GCP Cloud Logging for the gcp-bot Cloud Run service.
Focuses on Gemini, Web Search Indexing, Sheets, and Tag Manager failures.
"""

import os
import json
from datetime import datetime, timezone, timedelta
from google.cloud import logging as gcp_logging
from google.oauth2 import service_account

PROJECT_ID = "idx-lngndny"
SERVICE_NAME = "gcp-bot"

# Auth via Application Default Credentials (available in GH Actions via gcloud)
client = gcp_logging.Client(project=PROJECT_ID)

# Time window — last 24 hours
now = datetime.now(timezone.utc)
since = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

print(f"Pulling logs since: {since}\n")

# ── 1. Gemini errors ─────────────────────────────────────────
print("=" * 60)
print("GEMINI API ERRORS")
print("=" * 60)
filter_gemini = f"""
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE_NAME}"
severity>=ERROR
(textPayload=~"(?i)gemini" OR jsonPayload.message=~"(?i)gemini" OR textPayload=~"(?i)generativeai" OR textPayload=~"(?i)404" OR textPayload=~"(?i)model")
timestamp>="{since}"
"""
entries = list(client.list_entries(filter_=filter_gemini.strip(), max_results=20, order_by=gcp_logging.DESCENDING))
if entries:
    for e in entries:
        ts = e.timestamp.strftime("%H:%M:%S") if e.timestamp else "?"
        payload = e.payload if isinstance(e.payload, str) else json.dumps(e.payload)
        print(f"[{ts}] {payload[:300]}")
        print()
else:
    print("  (no Gemini error entries found in last 24h)")

# ── 2. Web Search Indexing errors ────────────────────────────
print("\n" + "=" * 60)
print("WEB SEARCH INDEXING API ERRORS")
print("=" * 60)
filter_indexing = f"""
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE_NAME}"
severity>=ERROR
(textPayload=~"(?i)index" OR textPayload=~"(?i)search.google" OR textPayload=~"(?i)indexing")
timestamp>="{since}"
"""
entries = list(client.list_entries(filter_=filter_indexing.strip(), max_results=20, order_by=gcp_logging.DESCENDING))
if entries:
    for e in entries:
        ts = e.timestamp.strftime("%H:%M:%S") if e.timestamp else "?"
        payload = e.payload if isinstance(e.payload, str) else json.dumps(e.payload)
        print(f"[{ts}] {payload[:300]}")
        print()
else:
    print("  (no Indexing error entries found in last 24h)")

# ── 3. Sheets errors ─────────────────────────────────────────
print("\n" + "=" * 60)
print("GOOGLE SHEETS API ERRORS")
print("=" * 60)
filter_sheets = f"""
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE_NAME}"
severity>=ERROR
(textPayload=~"(?i)sheet" OR textPayload=~"(?i)spreadsheet")
timestamp>="{since}"
"""
entries = list(client.list_entries(filter_=filter_sheets.strip(), max_results=20, order_by=gcp_logging.DESCENDING))
if entries:
    for e in entries:
        ts = e.timestamp.strftime("%H:%M:%S") if e.timestamp else "?"
        payload = e.payload if isinstance(e.payload, str) else json.dumps(e.payload)
        print(f"[{ts}] {payload[:300]}")
        print()
else:
    print("  (no Sheets error entries found in last 24h)")

# ── 4. Tag Manager errors ────────────────────────────────────
print("\n" + "=" * 60)
print("TAG MANAGER API ERRORS")
print("=" * 60)
filter_gtm = f"""
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE_NAME}"
severity>=ERROR
(textPayload=~"(?i)tag.manager" OR textPayload=~"(?i)tagmanager" OR textPayload=~"(?i)gtm")
timestamp>="{since}"
"""
entries = list(client.list_entries(filter_=filter_gtm.strip(), max_results=20, order_by=gcp_logging.DESCENDING))
if entries:
    for e in entries:
        ts = e.timestamp.strftime("%H:%M:%S") if e.timestamp else "?"
        payload = e.payload if isinstance(e.payload, str) else json.dumps(e.payload)
        print(f"[{ts}] {payload[:300]}")
        print()
else:
    print("  (no GTM error entries found in last 24h)")

# ── 5. All ERROR+ logs (catch-all) ───────────────────────────
print("\n" + "=" * 60)
print("ALL ERRORS (last 30 entries)")
print("=" * 60)
filter_all = f"""
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE_NAME}"
severity>=ERROR
timestamp>="{since}"
"""
entries = list(client.list_entries(filter_=filter_all.strip(), max_results=30, order_by=gcp_logging.DESCENDING))
if entries:
    for e in entries:
        ts = e.timestamp.strftime("%H:%M:%S") if e.timestamp else "?"
        sev = e.severity or "ERROR"
        payload = e.payload if isinstance(e.payload, str) else json.dumps(e.payload)
        print(f"[{ts}] [{sev}] {payload[:400]}")
        print()
else:
    print("  (no errors found in last 24h)")

print("\nDone.")
