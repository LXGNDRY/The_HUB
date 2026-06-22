#!/bin/bash
# =============================================================================
# Legendary Branding — GCP Secret Manager Setup
# Run this ONCE after audit call is cleared and you have live keys.
#
# Usage:
#   chmod +x setup_secrets.sh
#   ./setup_secrets.sh
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project idx-lngndny
# =============================================================================

set -e

PROJECT_ID="idx-lngndny"

echo "Setting up Secret Manager secrets for project: $PROJECT_ID"
echo ""

# Enable Secret Manager API (idempotent)
gcloud services enable secretmanager.googleapis.com --project=$PROJECT_ID

# ---------------------------------------------------------------------------
# Function: create or update a secret
# ---------------------------------------------------------------------------
create_or_update_secret() {
  local SECRET_NAME="$1"
  local PROMPT="$2"

  echo -n "$PROMPT: "
  read -s SECRET_VALUE
  echo ""

  # Check if secret exists
  if gcloud secrets describe "$SECRET_NAME" --project=$PROJECT_ID &>/dev/null; then
    echo "  → Updating existing secret: $SECRET_NAME"
    echo -n "$SECRET_VALUE" | gcloud secrets versions add "$SECRET_NAME" \
      --data-file=- \
      --project=$PROJECT_ID
  else
    echo "  → Creating new secret: $SECRET_NAME"
    echo -n "$SECRET_VALUE" | gcloud secrets create "$SECRET_NAME" \
      --data-file=- \
      --replication-policy=automatic \
      --project=$PROJECT_ID
  fi
  echo "  ✓ $SECRET_NAME saved"
  echo ""
}

# ---------------------------------------------------------------------------
# Razorpay Keys (get from dashboard after audit call green light)
# ---------------------------------------------------------------------------
create_or_update_secret "RAZORPAY_KEY_ID"     "Enter Razorpay Live Key ID (rzp_live_...)"
create_or_update_secret "RAZORPAY_KEY_SECRET" "Enter Razorpay Live Key Secret"
create_or_update_secret "WEBHOOK_SECRET"      "Enter Razorpay Webhook Secret (from Dashboard > Webhooks)"

# ---------------------------------------------------------------------------
# Shopify Admin Token
# Shopify Admin → Apps → Develop apps → lb-razorpay-backend → API credentials
# Scopes needed: write_orders, read_products, read_customers
# ---------------------------------------------------------------------------
create_or_update_secret "SHOPIFY_ADMIN_TOKEN" "Enter Shopify Admin API Token (shpat_...)"

# ---------------------------------------------------------------------------
# SFTP Key for invoice upload (get from Harish on audit call)
# Base64-encode the RSA private key PEM file first:
#   base64 -i razorpay_sftp_key.pem | tr -d '\n'
# ---------------------------------------------------------------------------
echo "For the SFTP private key, paste the base64-encoded PEM content."
echo "(Run: base64 -i your_private_key.pem | tr -d '\\n'  to generate it)"
create_or_update_secret "RZP_SFTP_PRIVATE_KEY" "Enter base64-encoded RSA private key"

# ---------------------------------------------------------------------------
# Grant Cloud Run service account access to all secrets
# ---------------------------------------------------------------------------
echo "Granting Cloud Run service account access to secrets..."

# Get the Cloud Run service account (default compute SA)
SA_EMAIL="${PROJECT_ID}@appspot.gserviceaccount.com"

for SECRET in RAZORPAY_KEY_ID RAZORPAY_KEY_SECRET WEBHOOK_SECRET SHOPIFY_ADMIN_TOKEN; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID \
    --quiet
  echo "  ✓ $SECRET → $SA_EMAIL"
done

echo ""
echo "============================================================"
echo "All secrets configured. You can now deploy Cloud Run:"
echo ""
echo "  cd razorpay-backend"
echo "  gcloud builds submit --config cloudbuild.yaml ."
echo ""
echo "After deploy, copy the Cloud Run URL and update in:"
echo "  cart-summary.liquid → var GCP_BASE = 'https://YOUR-GCP-CLOUDRUN-URL'"
echo "  Then also set: var RZP_KEY = 'rzp_live_...'"
echo "============================================================"
