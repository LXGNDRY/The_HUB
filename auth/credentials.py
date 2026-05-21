"""
auth/credentials.py — Credential resolution with three fallback layers.

Priority:
  1. GCP_SA_KEY_JSON env var — raw JSON string of a service account key
  2. GOOGLE_APPLICATION_CREDENTIALS env var — path to a SA key file
  3. Application Default Credentials (Cloud Run metadata server identity)
"""

import os
import json
from google.auth import default
from google.oauth2 import service_account

SCOPES = [
    # Core GCP
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/compute",
    "https://www.googleapis.com/auth/devstorage.read_write",
    "https://www.googleapis.com/auth/monitoring",
    "https://www.googleapis.com/auth/cloud-billing.readonly",
    # Google Sheets + Drive (sheets.py)
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    # Google Tag Manager (tag_manager.py)
    "https://www.googleapis.com/auth/tagmanager.readonly",
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.publish",
    # Web Search Indexing (indexing.py)
    "https://www.googleapis.com/auth/indexing",
    # Cloud Logging (cloud_logging.py)
    "https://www.googleapis.com/auth/logging.read",
    "https://www.googleapis.com/auth/logging.write",
    # Generative Language / Gemini API (gemini.py)
    "https://www.googleapis.com/auth/generative-language",
]


def get_credentials():
    """
    Returns Google credentials.

    1. GCP_SA_KEY_JSON — raw JSON string (set via --set-env-vars or Secret Manager)
    2. GOOGLE_APPLICATION_CREDENTIALS — path to SA key file
    3. ADC — Cloud Run attached service account (metadata server)
    """
    # Layer 1: raw JSON string in env var
    key_json = os.getenv("GCP_SA_KEY_JSON", "")
    if key_json:
        try:
            info = json.loads(key_json)
            return service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES
            )
        except Exception as e:
            import logging
            logging.getLogger("gcp-bot.auth").warning(
                "GCP_SA_KEY_JSON parse failed, falling back to ADC: %s", e
            )

    # Layer 2: file path
    key_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if key_file and os.path.isfile(key_file):
        return service_account.Credentials.from_service_account_file(
            key_file, scopes=SCOPES
        )

    # Layer 3: ADC (Cloud Run identity — metadata server)
    creds, _ = default(scopes=SCOPES)
    return creds
