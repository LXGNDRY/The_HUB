#!/bin/bash
# ============================================================
# GCP Bot — Cloud Run Deployment Script
# Run once from your project root to deploy.
# ============================================================

set -e

PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
SERVICE_NAME="gcp-bot"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "Deploying $SERVICE_NAME to Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo "Image:   $IMAGE"

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  containerregistry.googleapis.com \
  --project=$PROJECT_ID

# Build and push container image
gcloud builds submit --tag $IMAGE .

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID" \
  --memory 512Mi \
  --min-instances 1 \
  --max-instances 3 \
  --project=$PROJECT_ID

echo ""
echo "Deployment complete!"
echo "Service URL:"
gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)'
