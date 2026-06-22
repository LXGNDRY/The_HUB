"""
Legendary Branding — Razorpay SFTP Invoice Cloud Function
==========================================================
Triggered by: HTTP POST from Cloud Run webhook handler (payment.captured event)
              OR manually via GCP Cloud Scheduler post-launch.

Purpose:
  Generate a PDF invoice and upload to Razorpay SFTP for cross-border
  Import Flow compliance.

SFTP Path format (mandatory):
  /invoiceUpload/automated/<MerchantID>/<YYYY-MM-DD>/<InvoiceFileName>

  e.g. /invoiceUpload/automated/T3O33vNgpeDuO4/2026-06-23/INV-2026-1042.pdf

HS Codes:
  T-Shirts   → 6109.10
  Hoodies    → 6110.20
  Sweatpants → 6103.42

Environment (Secret Manager):
  RZP_SFTP_HOST          — sftp.razorpay.com (confirm with Harish on audit call)
  RZP_SFTP_USERNAME      — provided by Razorpay
  RZP_SFTP_PRIVATE_KEY   — RSA 2048-bit private key (PEM, base64-encoded in secret)
  RZP_MERCHANT_ID        — T3O33vNgpeDuO4
"""

import os
import io
import base64
import logging
import tempfile
from datetime import datetime, timezone

import paramiko
import functions_framework
from flask import Request
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SFTP_HOST       = os.environ.get("RZP_SFTP_HOST", "sftp.razorpay.com")
SFTP_PORT       = int(os.environ.get("RZP_SFTP_PORT", "22"))
SFTP_USERNAME   = os.environ.get("RZP_SFTP_USERNAME", "")
SFTP_KEY_B64    = os.environ.get("RZP_SFTP_PRIVATE_KEY", "")   # base64-encoded PEM
MERCHANT_ID     = os.environ.get("RZP_MERCHANT_ID", "T3O33vNgpeDuO4")

HS_CODES = {
    "t-shirt":     "6109.10",
    "tee":         "6109.10",
    "hoodie":      "6110.20",
    "sweatpants":  "6103.42",
    "jogger":      "6103.42",
    "default":     "6109.10"   # fallback — most items are tees
}

SELLER_INFO = {
    "name":    "Legendary Branding LLC",
    "address": "433 W Harrison St #5409, Chicago IL 60699, USA",
    "ein":     "85-4165134",
    "email":   "lb@legendary-branding.com",
    "website": "https://legendary-branding.com"
}


# ---------------------------------------------------------------------------
# PDF Invoice Generator
# ---------------------------------------------------------------------------

def get_hs_code(product_title: str) -> str:
    title_lower = product_title.lower()
    for keyword, code in HS_CODES.items():
        if keyword in title_lower:
            return code
    return HS_CODES["default"]


def generate_invoice_pdf(order: dict) -> bytes:
    """
    Generate a compliant PDF invoice for Razorpay cross-border.

    order dict expected keys:
      order_name        str   — e.g. #1042
      order_date        str   — ISO date
      customer_name     str
      customer_email    str
      shipping_address  dict
      line_items        list  — [{title, quantity, price_usd}]
      subtotal_usd      float
      shipping_usd      float
      total_usd         float
      razorpay_order_id str
      razorpay_payment_id str
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # --- Header ---
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20*mm, height - 25*mm, "LEGENDARY BRANDING")

    c.setFont("Helvetica", 9)
    c.drawString(20*mm, height - 32*mm, SELLER_INFO["address"])
    c.drawString(20*mm, height - 37*mm, f"Email: {SELLER_INFO['email']}  |  Web: {SELLER_INFO['website']}")
    c.drawString(20*mm, height - 42*mm, f"EIN: {SELLER_INFO['ein']}")

    # Invoice title + number
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(width - 20*mm, height - 25*mm, "COMMERCIAL INVOICE")

    c.setFont("Helvetica", 9)
    order_name = order.get("order_name", "")
    order_date = order.get("order_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    c.drawRightString(width - 20*mm, height - 32*mm, f"Invoice #: {order_name}")
    c.drawRightString(width - 20*mm, height - 37*mm, f"Date: {order_date}")
    c.drawRightString(width - 20*mm, height - 42*mm, f"Currency: USD")

    # Divider
    c.setLineWidth(0.5)
    c.line(20*mm, height - 47*mm, width - 20*mm, height - 47*mm)

    # --- Bill To ---
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20*mm, height - 54*mm, "BILL TO / SHIP TO:")
    c.setFont("Helvetica", 9)
    addr = order.get("shipping_address", {})
    y = height - 60*mm
    for line in [
        order.get("customer_name", ""),
        addr.get("address1", ""),
        f"{addr.get('city', '')}, {addr.get('country', '')} {addr.get('zip', '')}",
        order.get("customer_email", "")
    ]:
        if line.strip():
            c.drawString(20*mm, y, line)
            y -= 5*mm

    # --- Payment Reference ---
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(width - 20*mm, height - 54*mm, "PAYMENT REFERENCE:")
    c.setFont("Helvetica", 8)
    c.drawRightString(width - 20*mm, height - 59*mm, f"Razorpay Order: {order.get('razorpay_order_id', '')}")
    c.drawRightString(width - 20*mm, height - 64*mm, f"Razorpay Payment: {order.get('razorpay_payment_id', '')}")

    # --- Line Items Table ---
    table_top = height - 95*mm
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20*mm,            table_top, "DESCRIPTION")
    c.drawString(100*mm,           table_top, "HS CODE")
    c.drawCentredString(130*mm,    table_top, "QTY")
    c.drawRightString(160*mm,      table_top, "UNIT PRICE (USD)")
    c.drawRightString(width-20*mm, table_top, "TOTAL (USD)")

    c.line(20*mm, table_top - 2*mm, width - 20*mm, table_top - 2*mm)

    c.setFont("Helvetica", 9)
    y = table_top - 8*mm
    for item in order.get("line_items", []):
        title = item.get("title", "Product")
        qty   = int(item.get("quantity", 1))
        price = float(item.get("price_usd", 0))
        total = qty * price
        hs    = get_hs_code(title)

        c.drawString(20*mm,            y, title[:40])
        c.drawString(100*mm,           y, hs)
        c.drawCentredString(130*mm,    y, str(qty))
        c.drawRightString(160*mm,      y, f"${price:.2f}")
        c.drawRightString(width-20*mm, y, f"${total:.2f}")
        y -= 6*mm

    # Totals
    c.line(20*mm, y, width - 20*mm, y)
    y -= 6*mm
    c.setFont("Helvetica", 9)
    c.drawRightString(160*mm,      y, "Subtotal:")
    c.drawRightString(width-20*mm, y, f"${order.get('subtotal_usd', 0):.2f}")
    y -= 5*mm
    c.drawRightString(160*mm,      y, "Shipping:")
    c.drawRightString(width-20*mm, y, f"${order.get('shipping_usd', 0):.2f}")
    y -= 5*mm
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(160*mm,      y, "TOTAL (USD):")
    c.drawRightString(width-20*mm, y, f"${order.get('total_usd', 0):.2f}")

    # --- Footer ---
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    footer_text = (
        "This is a commercial invoice for customs purposes. "
        "Goods are of US origin. Payment processed via Razorpay Import Flow. "
        "Legendary Branding LLC, Chicago IL USA."
    )
    c.drawString(20*mm, 15*mm, footer_text)

    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# SFTP Upload
# ---------------------------------------------------------------------------

def upload_to_sftp(pdf_bytes: bytes, filename: str, date_str: str) -> str:
    """
    Upload invoice PDF to Razorpay SFTP.
    Returns the remote path on success.
    """
    # Decode private key from base64
    key_pem = base64.b64decode(SFTP_KEY_B64).decode("utf-8")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as kf:
        kf.write(key_pem)
        key_path = kf.name

    try:
        pkey = paramiko.RSAKey.from_private_key_file(key_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load SSH private key: {e}")

    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    try:
        transport.connect(username=SFTP_USERNAME, pkey=pkey)
        sftp = paramiko.SFTPClient.from_transport(transport)

        remote_dir = f"/invoiceUpload/automated/{MERCHANT_ID}/{date_str}"

        # Create date directory if it doesn't exist
        try:
            sftp.mkdir(remote_dir)
        except IOError:
            pass  # Directory already exists

        remote_path = f"{remote_dir}/{filename}"

        # Upload — do NOT upload same filename twice (Razorpay rejects duplicates)
        with io.BytesIO(pdf_bytes) as f:
            sftp.putfo(f, remote_path)

        log.info(f"Invoice uploaded: {remote_path}")
        sftp.close()
        return remote_path

    finally:
        transport.close()
        os.unlink(key_path)


# ---------------------------------------------------------------------------
# Cloud Function Entry Point
# ---------------------------------------------------------------------------

@functions_framework.http
def upload_invoice(request: Request):
    """
    HTTP-triggered Cloud Function.

    POST body (JSON) — same structure as generate_invoice_pdf() order dict.
    Called by Cloud Run /webhook handler on payment.captured event.
    """
    data = request.get_json(force=True, silent=True) or {}

    order_name  = data.get("order_name", "UNKNOWN")
    order_date  = data.get("order_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    log.info(f"Generating invoice for order {order_name}")

    try:
        pdf_bytes = generate_invoice_pdf(data)
    except Exception as e:
        log.error(f"PDF generation failed: {e}")
        return {"error": f"PDF generation failed: {e}"}, 500

    # Filename: INV-<date>-<order_number_digits>.pdf
    order_num = order_name.replace("#", "").strip()
    filename  = f"INV-{order_date}-{order_num}.pdf"

    try:
        remote_path = upload_to_sftp(pdf_bytes, filename, order_date)
    except Exception as e:
        log.error(f"SFTP upload failed: {e}")
        return {"error": f"SFTP upload failed: {e}"}, 500

    return {
        "success": True,
        "remote_path": remote_path,
        "filename": filename
    }, 200
