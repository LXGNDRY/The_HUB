"""
sftp_upload.py — Upload Razorpay payment invoice CSV to supplier SFTP.

Called in a background thread from main.py on payment.captured events.
The private key is read from the RAZORPAY_SFTP_PRIVATE_KEY env var (injected
from GCP Secret Manager at runtime). Host/user/path are read from env vars
with sensible defaults that can be overridden without redeploying.
"""

import csv
import io
import logging
import os
import tempfile
import time

import paramiko

log = logging.getLogger(__name__)

SFTP_HOST     = os.environ.get("SFTP_HOST", "")
SFTP_PORT     = int(os.environ.get("SFTP_PORT", "22"))
SFTP_USER     = os.environ.get("SFTP_USER", "")
SFTP_PATH     = os.environ.get("SFTP_UPLOAD_PATH", "/invoices/")
SFTP_KEY_ENV  = "RAZORPAY_SFTP_PRIVATE_KEY"


def _get_private_key() -> paramiko.PKey:
    """Load RSA/Ed25519 private key from env var."""
    pem = os.environ.get(SFTP_KEY_ENV, "").strip()
    if not pem:
        raise ValueError(f"{SFTP_KEY_ENV} env var is empty or not set")

    key_file = io.StringIO(pem)
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            key_file.seek(0)
            return cls.from_private_key(key_file)
        except Exception:
            continue
    raise ValueError("Could not parse private key — expected Ed25519, RSA, or ECDSA PEM")


def _build_csv(records: list[dict]) -> str:
    """Convert payment records to CSV string."""
    if not records:
        return ""
    fields = list(records[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue()


def upload_invoice(records: list[dict]) -> str:
    """
    Upload payment records as a CSV to the supplier SFTP server.

    Args:
        records: list of payment dicts (payment_id, order_id, amount_paise, …)

    Returns:
        Remote filename on success.

    Raises:
        Exception on any failure (caller logs and ignores — non-fatal).
    """
    if not SFTP_HOST or not SFTP_USER:
        raise ValueError("SFTP_HOST and SFTP_USER env vars must be set")

    csv_content = _build_csv(records)
    filename = f"lb_invoice_{int(time.time())}.csv"
    remote_path = os.path.join(SFTP_PATH, filename)

    key = _get_private_key()

    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    try:
        transport.connect(username=SFTP_USER, pkey=key)
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
                tmp.write(csv_content)
                tmp_path = tmp.name
            sftp.put(tmp_path, remote_path)
            os.unlink(tmp_path)
            log.info(f"SFTP upload complete: {remote_path}")
        finally:
            sftp.close()
    finally:
        transport.close()

    return filename
