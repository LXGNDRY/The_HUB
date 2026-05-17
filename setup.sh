#!/usr/bin/env bash
# =============================================================
# GCP Bot — Full Setup Script
# Legendary Branding Infrastructure
# =============================================================
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
# =============================================================

set -e  # Exit on any error

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[setup]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $1"; }
err()  { echo -e "${RED}[error]${NC} $1"; exit 1; }

echo ""
echo "======================================================"
echo "  GCP Bot Setup — Legendary Branding"
echo "======================================================"
echo ""

# ────────────────────────────────────────────────────────
# 1. Check prerequisites
# ────────────────────────────────────────────────────────
log "Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || err "python3 is required but not installed."
command -v pip    >/dev/null 2>&1 || err "pip is required but not installed."
command -v gcloud >/dev/null 2>&1 || warn "gcloud CLI not found — GCS bucket creation will be skipped."

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
log "Python $PYTHON_VERSION detected"

# ────────────────────────────────────────────────────────
# 2. Virtual environment
# ────────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    log "Creating virtual environment..."
    python3 -m venv venv
else
    log "Virtual environment already exists — skipping creation"
fi

log "Activating venv and installing dependencies..."
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
log "Dependencies installed ✓"

# ────────────────────────────────────────────────────────
# 3. Environment file
# ────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn ".env created from .env.example — fill in your values before running agents."
else
    log ".env already exists — skipping"
fi

# ────────────────────────────────────────────────────────
# 4. Auth folder
# ────────────────────────────────────────────────────────
mkdir -p auth reports
if [ ! -f "auth/service_account.json" ]; then
    warn "auth/service_account.json not found."
    warn "Download your GCP Service Account key and place it at: auth/service_account.json"
else
    log "Service account key found ✓"
fi

# ────────────────────────────────────────────────────────
# 5. GCS Bucket creation
# ────────────────────────────────────────────────────────
if command -v gcloud >/dev/null 2>&1; then
    # Load bucket name from .env if available
    if [ -f ".env" ]; then
        THEME_BUCKET=$(grep '^THEME_BUCKET=' .env | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    fi
    THEME_BUCKET=${THEME_BUCKET:-legendary-branding-themes}
    LOCATION="us-central1"

    log "Checking GCS bucket: gs://$THEME_BUCKET ..."
    if gcloud storage buckets describe "gs://$THEME_BUCKET" >/dev/null 2>&1; then
        log "Bucket gs://$THEME_BUCKET already exists – skipping creation"
    else
        log "Creating GCS bucket: gs://$THEME_BUCKET in $LOCATION ..."
        gcloud storage buckets create "gs://$THEME_BUCKET" \
            --location="$LOCATION" \
            --uniform-bucket-level-access \
            --public-access-prevention
        log "Bucket gs://$THEME_BUCKET created ✓"

        # Create placeholder objects to establish folder structure
        log "Initializing bucket folder structure..."
        echo "# GCP Bot theme live snapshot" | \
            gcloud storage cp - "gs://$THEME_BUCKET/live/.keep" --quiet
        echo "# GCP Bot theme versions archive" | \
            gcloud storage cp - "gs://$THEME_BUCKET/versions/.keep" --quiet
        log "Bucket structure initialized ✓"
    fi
else
    warn "gcloud not found — skipping bucket creation."
    warn "Run manually: gcloud storage buckets create gs://legendary-branding-themes --location=us-central1"
fi

# ────────────────────────────────────────────────────────
# 6. Validate .env is filled in
# ────────────────────────────────────────────────────────
log "Validating .env configuration..."

MISSING=0
check_env() {
    local key=$1
    local val=$(grep "^$key=" .env 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    if [ -z "$val" ] || [ "$val" = "your-gcp-project-id" ] || [[ "$val" == *"XXXX"* ]]; then
        warn "  $key is not set — update .env before running"
        MISSING=$((MISSING + 1))
    else
        log "  $key ✓"
    fi
}

check_env "GCP_PROJECT_ID"
check_env "THEME_BUCKET"
check_env "SHOPIFY_STORE"
check_env "SHOPIFY_ADMIN_TOKEN"

if [ $MISSING -gt 0 ]; then
    warn "$MISSING variable(s) still need to be filled in .env"
else
    log "All required .env variables are set ✓"
fi

# ────────────────────────────────────────────────────────
# Done
# ────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo -e "  ${GREEN}Setup complete!${NC}"
echo "======================================================"
echo ""
echo "  Next steps:"
echo "  1. Place your service account key at: auth/service_account.json"
echo "  2. Fill in any remaining .env values"
echo "  3. Activate venv:  source venv/bin/activate"
echo ""
echo "  Quick test commands:"
echo "    python cli.py billing-info"
echo "    python cli.py list-all-vms"
echo "    python cli.py versions"
echo ""
