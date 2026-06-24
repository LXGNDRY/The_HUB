"""
sftp_upload.py
Legendary Branding — Razorpay SFTP Invoice Uploader
====================================================
Generates a Razorpay-compatible invoice CSV and uploads it to the
Razorpay SFTP server via paramiko (SSH).

SFTP credentials (from Sakshi Mishra, Razorpay Solutions Engineer, Jun 24 2026):
  Host:     s-20628a7a7d07456a8.server.transfer.ap-south-1.amazonaws.com
  Port:     22
  Username: rzp-legendary-sftp
  Path:     /rzp-1415-prod-sftp/invoiceUpload/automated/T3O33vNgpeDuO4
            (server jails you to this directory on login — no cd needed)

Auth:
  ED25519 private key stored in GCP Secret Manager as RAZORPAY_SFTP_PRIVATE_KEY
  Public key: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFBSyyEPCWzrWkXvvgJu3YAVTmHUOpYnonK3erxtvYEM

Invoice format:
  Razorpay expects a UTF-8 CSV with specific column headers.
  Each row = one payment captured event.
  File naming: LB_invoices_YYYYMMDD_HHMMSS.csv
"""

import csv
import io
import os
import logging
import tempfile
import paramiko
from datetime import datetime, timezone
from google.cloud import secretmanager

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SFTP config
# ---------------------------------------------------------------------------
SFTP_HOST     = "s-20628a7a7d07456a8.server.transfer.ap-south-1.amazonaws.com"
SFTP_PORT     = 22
SFTP_USERNAME = "rzp-legendary-sftp"
# Server jails to path prefix on login — upload files directly to root of session
SFTP_PATH     = "."   # working dir is already the invoice path

GCP_PROJECT_ID      = os.environ.get("GCP_PROJECT_ID", "idx-lngndny")
SFTP_SECRET_NAME    = "RAZORPAY_SFTP_PRIVATE_KEY"

# ---------------------------------------------------------------------------
# Invoice CSV columns (Razorpay import format)
# ---------------------------------------------------------------------------
INVOICE_COLUMNS = [
    "payment_id",
    "order_id",
    "amount",           # in rupees (not paise)
    "currency",
    "status",
    "method",
    "email",
    "contact",
    "description",
    "created_at",       # ISO 8601 UTC
    "merchant_order_id",
    "shopify_order_name",
]


def _get_sftp_private_key() -> paramiko.Ed25519Key:
    """Retrieve ED25519 private key from GCP Secret Manager."""
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{GCP_PROJECT_ID}/secrets/{SFTP_SECRET_NAME}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        key_pem = response.payload.data.decode("utf-8").strip()

        # Write to temp file — paramiko needs a file path or file-like object
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(key_pem)
            tmp_path = f.name

        key = paramiko.Ed25519Key.from_private_key_file(tmp_path)
        os.unlink(tmp_path)
        return key

    except Exception as e:
        log.error(f"Failed to load SFTP private key from Secret Manager: {e}")
        raise


def _build_invoice_csv(payments: list[dict]) -> str:
    """
    Build a UTF-8 CSV string from a list of payment dicts.

    Each payment dict should contain:
      payment_id, order_id, amount_paise, currency, status, method,
      email, contact, description, created_at (unix ts), merchant_order_id,
      shopify_order_name
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=INVOICE_COLUMNS, extrasaction="ignore")
    writer.writeheader()

    for p in payments:
        # Convert paise → rupees
        amount_rupees = round(int(p.get("amount_paise", 0)) / 100, 2)

        # Convert unix timestamp → ISO 8601 UTC
        created_ts = p.get("created_at", 0)
        if isinstance(created_ts, (int, float)) and created_ts > 0:
            created_iso = datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat()
        else:
            created_iso = datetime.now(tz=timezone.utc).isoformat()

        writer.writerow({
            "payment_id":          p.get("payment_id", ""),
            "order_id":            p.get("order_id", ""),
            "amount":              f"{amount_rupees:.2f}",
            "currency":            p.get("currency", "INR"),
            "status":              p.get("status", "captured"),
            "method":              p.get("method", ""),
            "email":               p.get("email", ""),
            "contact":             p.get("contact", ""),
            "description":         p.get("description", "Legendary Branding"),
            "created_at":          created_iso,
            "merchant_order_id":   p.get("merchant_order_id", ""),
            "shopify_order_name":  p.get("shopify_order_name", ""),
        })

    return output.getvalue()


def upload_invoice(payments: list[dict]) -> str:
    """
    Build an invoice CSV from `payments` and upload to Razorpay SFTP.

    Returns the remote filename on success.
    Raises on connection or upload failure.

    Usage (from webhook handler):
        from sftp.sftp_upload import upload_invoice
        filename = upload_invoice([{
            "payment_id": "pay_xxx",
            "order_id": "order_xxx",
            "amount_paise": 1180000,   # ₹11,800
            "currency": "INR",
            "status": "captured",
            "method": "upi",
            "email": "customer@example.com",
            "contact": "+91xxxxxxxxxx",
            "description": "Legendary Branding",
            "created_at": 1719216000,
            "merchant_order_id": "lb_abc123",
            "shopify_order_name": "#1042",
        }])
    """
    if not payments:
        log.warning("upload_invoice called with empty payments list — skipping")
        return ""

    # Generate filename: LB_invoices_YYYYMMDD_HHMMSS_<payment_id>.csv
    now_str  = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    first_id = payments[0].get("payment_id", "batch")
    filename = f"LB_invoices_{now_str}_{first_id}.csv"

    csv_content = _build_invoice_csv(payments)
    log.info(f"Invoice CSV built: {len(payments)} row(s), filename={filename}")

    # Connect and upload
    private_key = _get_sftp_private_key()

    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    try:
        transport.connect(username=SFTP_USERNAME, pkey=private_key)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # Write CSV to remote file directly from string
        with sftp.open(filename, "w") as remote_file:
            remote_file.write(csv_content)

        log.info(f"Invoice uploaded successfully: {filename}")
        sftp.close()
        return filename

    except Exception as e:
        log.error(f"SFTP upload failed: {e}")
        raise
    finally:
        transport.close()


def upload_invoice_batch(payments: list[dict]) -> list[str]:
    """
    Upload multiple invoices. Batches by day to keep files manageable.
    Returns list of uploaded filenames.
    """
    if not payments:
        return []

    # Group by date
    from collections import defaultdict
    by_date: dict[str, list] = defaultdict(list)
    for p in payments:
        ts = p.get("created_at", 0)
        date_key = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d") if ts else "unknown"
        by_date[date_key].append(p)

    uploaded = []
    for date_key, batch in by_date.items():
        try:
            filename = upload_invoice(batch)
            uploaded.append(filename)
        except Exception as e:
            log.error(f"Batch upload failed for date {date_key}: {e}")

    return uploaded
