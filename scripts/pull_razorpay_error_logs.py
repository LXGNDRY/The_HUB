#!/usr/bin/env python3
"""
pull_razorpay_error_logs.py
Pulls recent error logs from GCP Cloud Logging for the lb-razorpay-backend Cloud Run service.
Focuses on payment, verify, signature, Shopify, and Klaviyo failures.
"""

import os
import json
from datetime import datetime, timezone, timedelta
from google.cloud import logging as gcp_logging

PROJECT_ID = "idx-lngndny"
SERVICE_NAME = "lb-razorpay-backend"

client = gcp_logging.Client(project=PROJECT_ID)

now = datetime.now(timezone.utc)
since = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

print(f"Pulling logs since: {since}\n")


def dump_entries(label, filter_str, max_results=20):
    print("=" * 60)
    print(label)
    print("=" * 60)
    entries = list(client.list_entries(filter_=filter_str.strip(), max_results=max_results, order_by=gcp_logging.DESCENDING))
    if entries:
        for e in entries:
            ts = e.timestamp.strftime("%H:%M:%S") if e.timestamp else "?"
            sev = getattr(e, "severity", "ERROR") or "ERROR"
            payload = e.payload if isinstance(e.payload, str) else json.dumps(e.payload)
            print(f"[{ts}] [{sev}] {payload[:400]}")
            print()
    else:
        print(f"  (no entries found in last 24h)")


dump_entries("PAYMENT FAILURES", f"""
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE_NAME}"
severity>=WARNING
(textPayload=~"(?i)payment" OR textPayload=~"(?i)failed" OR textPayload=~"(?i)razorpay")
timestamp>="{since}"
""")

dump_entries("VERIFY / SIGNATURE ERRORS", f"""
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE_NAME}"
severity>=ERROR
(textPayload=~"(?i)verify" OR textPayload=~"(?i)signature" OR textPayload=~"(?i)hmac")
timestamp>="{since}"
""")

dump_entries("SHOPIFY ORDER ERRORS", f"""
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE_NAME}"
severity>=ERROR
(textPayload=~"(?i)shopify" OR textPayload=~"(?i)draft.order" OR textPayload=~"(?i)order")
timestamp>="{since}"
""")

dump_entries("KLAVIYO ERRORS", f"""
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE_NAME}"
severity>=ERROR
(textPayload=~"(?i)klaviyo" OR textPayload=~"(?i)checkout.started" OR textPayload=~"(?i)abandoned")
timestamp>="{since}"
""")

dump_entries("ALL ERRORS (last 40 entries)", f"""
resource.type="cloud_run_revision"
resource.labels.service_name="{SERVICE_NAME}"
severity>=ERROR
timestamp>="{since}"
""", max_results=40)

print("\nDone.")
