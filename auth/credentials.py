"""
auth/credentials.py — Application Default Credentials helper.
"""

import os
from google.auth import default
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/compute",
    "https://www.googleapis.com/auth/devstorage.read_write",
    "https://www.googleapis.com/auth/monitoring",
    "https://www.googleapis.com/auth/cloud-billing.readonly",
]


def get_credentials():
    """
    Returns Google credentials.
    - If GOOGLE_APPLICATION_CREDENTIALS is set, uses that service account file.
    - Otherwise falls back to Application Default Credentials (Cloud Run identity).
    """
    key_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if key_file and os.path.exists(key_file):
        return service_account.Credentials.from_service_account_file(
            key_file, scopes=SCOPES
        )
    creds, _ = default(scopes=SCOPES)
    return creds
