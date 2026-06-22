#!/bin/bash
# =============================================================================
# Legendary Branding — GO LIVE
# Run this after audit call green light from Harish.
#
# What this does (in order):
#   1. Loads 4 secrets into GCP Secret Manager
#   2. Deploys Cloud Run backend
#   3. Prints the Cloud Run URL
#   4. Reminds you of the 2 manual steps after deploy
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project idx-lngndny
#
# Usage:
#   chmod +x go_live.sh
#   ./go_live.sh
# =============================================================================

set -e
PROJECT_ID="idx-lngndny"
SERVICE_NAME="lb-razorpay-backend"
REGION="us-central1"

echo ""
echo "============================================================"
echo "  LEGENDARY BRANDING — RAZORPAY GO LIVE"
echo "============================================================"
echo ""

# ── Step 1: Secrets ──────────────────────────────────────────────
echo "STEP 1 of 3 — Loading secrets into GCP Secret Manager"
echo ""

gcloud services enable secretmanager.googleapis.com --project=$PROJECT_ID --quiet

load_secret() {
  local NAME="$1" PROMPT="$2"
  echo -n "  $PROMPT: "
  read -s VALUE; echo ""
  if gcloud secrets describe "$NAME" --project=$PROJECT_ID &>/dev/null; then
    echo -n "$VALUE" | gcloud secrets versions add "$NAME" --data-file=- --project=$PROJECT_ID --quiet
  else
    echo -n "$VALUE" | gcloud secrets create "$NAME" --data-file=- --replication-policy=automatic --project=$PROJECT_ID --quiet
  fi
  echo "  ✓ $NAME saved"
}

load_secret "RAZORPAY_KEY_ID"     "Razorpay Live Key ID (rzp_live_...)"
load_secret "RAZORPAY_KEY_SECRET" "Razorpay Live Key Secret"
load_secret "WEBHOOK_SECRET"      "Razorpay Webhook Secret (from Dashboard → Webhooks)"
load_secret "SHOPIFY_ADMIN_TOKEN" "Shopify Admin Token (shpat_... from lb-razorpay-backend app)"

# Grant Cloud Run SA access
SA_EMAIL=$(gcloud iam service-accounts list --project=$PROJECT_ID --filter="displayName:Compute Engine default" --format="value(email)" 2>/dev/null || echo "${PROJECT_ID}@appspot.gserviceaccount.com")
for SECRET in RAZORPAY_KEY_ID RAZORPAY_KEY_SECRET WEBHOOK_SECRET SHOPIFY_ADMIN_TOKEN; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID --quiet 2>/dev/null || true
done
echo "  ✓ Secret Manager IAM bindings set"
echo ""

# ── Step 2: Deploy Cloud Run ─────────────────────────────────────
echo "STEP 2 of 3 — Deploying Cloud Run backend"
echo ""

cd "$(dirname "$0")/.."
gcloud builds submit --config cloudbuild.yaml . --project=$PROJECT_ID

# Get the deployed URL
CLOUD_RUN_URL=$(gcloud run services describe $SERVICE_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --format="value(status.url)" 2>/dev/null)

echo ""
echo "  ✓ Cloud Run deployed"
echo "  ✓ URL: $CLOUD_RUN_URL"
echo ""

# ── Step 3: Print manual steps ───────────────────────────────────
echo "STEP 3 of 3 — Two manual steps remaining"
echo ""
echo "  ─────────────────────────────────────────────────────────"
echo "  A) Swap placeholders in LegendaryBrandingTHEME dev branch:"
echo ""
echo "     In snippets/cart-summary.liquid, replace:"
echo "       var GCP_BASE = 'https://YOUR-GCP-CLOUDRUN-URL';"
echo "     with:"
echo "       var GCP_BASE = '$CLOUD_RUN_URL';"
echo ""
echo "     And replace:"
echo "       var RZP_KEY = 'YOUR_RAZORPAY_KEY_ID';"
echo "     with your live rzp_live_... key"
echo ""
echo "  B) In Razorpay Dashboard:"
echo "     → Account & Settings → Webhooks → Add webhook:"
echo "       URL:    $CLOUD_RUN_URL/webhook"
echo "       Events: payment.captured, payment.failed, order.paid"
echo ""
echo "     → Account & Settings → Payment Capture:"
echo "       Enable Auto Capture"
echo ""
echo "  ─────────────────────────────────────────────────────────"
echo ""
echo "  After A and B — merge dev → main, preview → live."
echo "  You're live. 🔥"
echo ""
echo "============================================================"
