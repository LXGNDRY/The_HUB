#!/usr/bin/env python3
"""
generate_google_ads_refresh_token.py — Legendary Branding

One-time, interactive script to mint a Google Ads API OAuth refresh token.

The Google Ads API does not support service-account/GCP-IAM auth — it only
accepts OAuth 2.0 user credentials (a refresh token tied to the Google
account that has access to the Ads account or its manager account). This
script runs the standard installed-app OAuth flow locally: it opens your
browser, you log in with that Google account and grant consent, and it
prints the refresh token to paste into the GOOGLE_ADS_REFRESH_TOKEN GitHub
secret. This only needs to be run once — the resulting token does not expire
under normal use (only if revoked, or unused for 6 months).

Requires locally:
  pip install google-auth-oauthlib

Usage:
  GOOGLE_ADS_CLIENT_ID=... GOOGLE_ADS_CLIENT_SECRET=... \\
    python scripts/generate_google_ads_refresh_token.py

Run this on your own machine (not in CI) — it opens a local browser window.
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main():
    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("ERROR: Set GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET env vars first.", file=sys.stderr)
        print("These are the same OAuth client credentials already stored as GitHub secrets —", file=sys.stderr)
        print("copy their values from Settings -> Secrets and variables -> Actions.", file=sys.stderr)
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    print()
    print("A browser window will open. Log in with the Google account that has")
    print("access to the Google Ads account (customer ID 1137623123) or its")
    print("manager account, then grant consent.")
    print()

    creds = flow.run_local_server(port=0)

    print()
    print("=" * 70)
    print("SUCCESS — copy this refresh token into the GOOGLE_ADS_REFRESH_TOKEN")
    print("GitHub secret (Settings -> Secrets and variables -> Actions):")
    print("=" * 70)
    print()
    print(creds.refresh_token)
    print()


if __name__ == "__main__":
    main()
