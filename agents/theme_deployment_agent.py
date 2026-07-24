"""
Theme Deployment Agent
======================
Automates deploying, updating, and rolling back Shopify themes
to your Google Cloud Storage bucket (for backup/versioning)
and optionally triggers Shopify Theme API deployments.

Modules:
  - Upload theme files to GCS bucket
  - List / compare theme versions
  - Rollback to a previous version
  - Notify via Slack/Discord webhook on deploy

Requires:
  - GCS bucket already created (set THEME_BUCKET in .env)
  - Shopify API credentials (set in .env) for live deploy
  - Service account with roles/storage.objectAdmin
"""

import os
import json
import hashlib
import datetime
from pathlib import Path
from typing import Optional

from google.cloud import storage
from google.oauth2 import service_account
from dotenv import load_dotenv

import requests

load_dotenv()

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
PROJECT_ID        = os.getenv("GCP_PROJECT_ID")
CREDENTIALS_PATH  = os.getenv("GCP_CREDENTIALS_PATH", "auth/service_account.json")
THEME_BUCKET      = os.getenv("THEME_BUCKET")              # e.g. "legendary-branding-themes"
SHOPIFY_STORE     = os.getenv("SHOPIFY_STORE")             # e.g. "yourstore.myshopify.com"
SHOPIFY_TOKEN     = os.getenv("SHOPIFY_ADMIN_TOKEN")       # Admin API access token
WEBHOOK_URL       = os.getenv("DEPLOY_WEBHOOK_URL", "")    # Slack or Discord webhook
DEPLOY_SCOPES     = ["https://www.googleapis.com/auth/cloud-platform"]


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────
def get_credentials() -> service_account.Credentials:
    """Load GCP service account credentials."""
    return service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH, scopes=DEPLOY_SCOPES
    )


def get_storage_client() -> storage.Client:
    return storage.Client(project=PROJECT_ID, credentials=get_credentials())


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def file_checksum(filepath: str) -> str:
    """SHA256 checksum of a local file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def timestamp_prefix() -> str:
    """Returns UTC timestamp string for versioned GCS paths."""
    return datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def send_notification(message: str) -> None:
    """POST a message to Slack or Discord webhook."""
    if not WEBHOOK_URL:
        return
    payload = {"content": message} if "discord" in WEBHOOK_URL else {"text": message}
    try:
        requests.post(WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"[notify] Webhook failed: {e}")


# ─────────────────────────────────────────────
# Core Agent Class
# ─────────────────────────────────────────────
class ThemeDeploymentAgent:
    """
    Manages Shopify theme deployments backed by Google Cloud Storage.

    GCS structure:
        gs://{THEME_BUCKET}/
            live/              ← current live theme snapshot
            versions/
                20240517T120000Z/   ← timestamped version archives
                    assets/
                    config/
                    layout/
                    sections/
                    snippets/
                    templates/
                    meta.json
    """

    def __init__(self):
        self.client  = get_storage_client()
        self.bucket  = self.client.bucket(THEME_BUCKET)

    # ── Upload ──────────────────────────────
    def upload_theme(self, theme_dir: str, label: Optional[str] = None) -> str:
        """
        Upload all files from a local theme directory to GCS.
        Saves under versions/{timestamp}/ and overwrites live/.

        Args:
            theme_dir: Local path to your Shopify theme folder.
            label:     Optional human-readable tag (e.g. "summer-drop-v2").

        Returns:
            The GCS version prefix (e.g. "versions/20240517T120000Z").
        """
        version_id  = timestamp_prefix()
        version_pfx = f"versions/{version_id}"
        theme_path  = Path(theme_dir)

        if not theme_path.is_dir():
            raise ValueError(f"Theme directory not found: {theme_dir}")

        uploaded_files = []
        for file_path in theme_path.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(theme_path)
                gcs_version_key = f"{version_pfx}/{relative}"
                gcs_live_key    = f"live/{relative}"

                # Upload to versioned archive
                blob = self.bucket.blob(gcs_version_key)
                blob.upload_from_filename(str(file_path))

                # Overwrite live snapshot
                live_blob = self.bucket.blob(gcs_live_key)
                live_blob.upload_from_filename(str(file_path))

                uploaded_files.append(str(relative))
                print(f"  [upload] {relative}")

        # Write version metadata
        meta = {
            "version_id":   version_id,
            "label":        label or version_id,
            "deployed_at":  datetime.datetime.utcnow().isoformat() + "Z",
            "file_count":   len(uploaded_files),
            "files":        uploaded_files,
        }
        meta_blob = self.bucket.blob(f"{version_pfx}/meta.json")
        meta_blob.upload_from_string(json.dumps(meta, indent=2), content_type="application/json")

        msg = f"✅ Theme deployed | version: {version_id} | label: {meta['label']} | {len(uploaded_files)} files"
        print(msg)
        send_notification(msg)
        return version_pfx

    # ── List Versions ────────────────────────
    def list_versions(self, limit: int = 10) -> list[dict]:
        """
        List the most recent theme versions stored in GCS.

        Returns:
            List of version metadata dicts, newest first.
        """
        blobs = self.client.list_blobs(THEME_BUCKET, prefix="versions/", delimiter="/")
        prefixes = sorted(
            [p for p in blobs.prefixes],
            reverse=True
        )[:limit]

        versions = []
        for pfx in prefixes:
            meta_blob = self.bucket.blob(f"{pfx}meta.json")
            if meta_blob.exists():
                meta = json.loads(meta_blob.download_as_text())
                versions.append(meta)
        return versions

    # ── Rollback ─────────────────────────────
    def rollback(self, version_id: str) -> None:
        """
        Roll back the live/ snapshot to a specific archived version.

        Args:
            version_id: Timestamp string, e.g. "20240517T120000Z".
        """
        version_pfx = f"versions/{version_id}/"
        blobs = list(self.client.list_blobs(THEME_BUCKET, prefix=version_pfx))

        if not blobs:
            raise ValueError(f"Version not found in GCS: {version_id}")

        rolled_back = []
        for blob in blobs:
            if blob.name.endswith("meta.json"):
                continue
            relative = blob.name[len(version_pfx):]
            self.bucket.copy_blob(blob, self.bucket, f"live/{relative}")
            rolled_back.append(relative)
            print(f"  [rollback] {relative}")

        msg = f"⏪ Rollback complete | version: {version_id} | {len(rolled_back)} files restored"
        print(msg)
        send_notification(msg)

    # ── Download Live Theme ───────────────────
    def download_live(self, dest_dir: str) -> None:
        """
        Download the current live/ theme snapshot to a local directory.

        Args:
            dest_dir: Local path to write files into.
        """
        dest_path = Path(dest_dir)
        dest_path.mkdir(parents=True, exist_ok=True)
        blobs = list(self.client.list_blobs(THEME_BUCKET, prefix="live/"))

        for blob in blobs:
            relative = blob.name[len("live/"):]
            if not relative:
                continue
            local_file = dest_path / relative
            local_file.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(local_file))
            print(f"  [download] {relative}")

        print(f"✅ Live theme downloaded to: {dest_dir}")

    # ── Shopify Live Push ─────────────────────
    def push_to_shopify(self, theme_dir: str, shopify_theme_id: str) -> None:
        """
        Push local theme files directly to a Shopify theme via Admin API.
        Requires SHOPIFY_STORE and SHOPIFY_ADMIN_TOKEN in .env.

        Args:
            theme_dir:        Local theme directory.
            shopify_theme_id: Shopify theme ID (find in Themes admin page URL).
        """
        if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
            raise EnvironmentError("SHOPIFY_STORE and SHOPIFY_ADMIN_TOKEN must be set in .env")

        theme_path = Path(theme_dir)
        base_url = f"https://{SHOPIFY_STORE}/admin/api/2026-04/themes/{shopify_theme_id}/assets.json"
        headers  = {
            "X-Shopify-Access-Token": SHOPIFY_TOKEN,
            "Content-Type": "application/json",
        }

        SHOPIFY_ASSET_DIRS = {"assets", "config", "layout", "sections", "snippets", "templates", "locales"}

        pushed = 0
        failed = 0
        for file_path in theme_path.rglob("*"):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(theme_path)
            top_dir  = relative.parts[0] if relative.parts else ""
            if top_dir not in SHOPIFY_ASSET_DIRS:
                continue

            key = str(relative).replace("\\", "/")
            try:
                content = file_path.read_bytes()
                # Shopify API: text files use 'value', binary use 'attachment' (base64)
                try:
                    value   = content.decode("utf-8")
                    payload = {"asset": {"key": key, "value": value}}
                except UnicodeDecodeError:
                    import base64
                    payload = {"asset": {"key": key, "attachment": base64.b64encode(content).decode()}}

                resp = requests.put(base_url, headers=headers, json=payload, timeout=30)
                if resp.status_code in (200, 201):
                    print(f"  [shopify] ✓ {key}")
                    pushed += 1
                else:
                    print(f"  [shopify] ✗ {key} — {resp.status_code}: {resp.text[:100]}")
                    failed += 1
            except Exception as e:
                print(f"  [shopify] error on {key}: {e}")
                failed += 1

        msg = f"🛍 Shopify push complete | {pushed} succeeded | {failed} failed"
        print(msg)
        send_notification(msg)

    # ── Diff Versions ─────────────────────────
    def diff_versions(self, version_a: str, version_b: str) -> dict:
        """
        Compare file lists between two archived versions.

        Returns:
            Dict with keys 'added', 'removed', 'common'.
        """
        def get_files(version_id):
            meta_blob = self.bucket.blob(f"versions/{version_id}/meta.json")
            if not meta_blob.exists():
                raise ValueError(f"Version not found: {version_id}")
            return set(json.loads(meta_blob.download_as_text())["files"])

        files_a = get_files(version_a)
        files_b = get_files(version_b)
        return {
            "added":   list(files_b - files_a),
            "removed": list(files_a - files_b),
            "common":  list(files_a & files_b),
        }
