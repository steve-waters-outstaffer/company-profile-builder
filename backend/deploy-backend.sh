#!/bin/bash

# Configuration
PROJECT_ID="gen-lang-client-0048564118"
SERVICE_NAME="company-researcher"
REGION="us-central1"
DOCKERFILE_PATH="." # Dockerfile is in the current (backend) folder

# --- !! REQUIRED !! ---
# 1. Get this from the Cloud Run dashboard AFTER your first deploy.
#    e.g., https://company-researcher-nq747c2jla-uc.a.run.app
export CLOUD_RUN_SERVICE_URL="https://company-researcher-373126702591.us-central1.run.app"

# 2. Get this from the GCP IAM & Admin dashboard.
export SERVICE_ACCOUNT_EMAIL="373126702591-compute@developer.gserviceaccount.com"

# --- Check for empty variables ---
if [ -z "$CLOUD_RUN_SERVICE_URL" ] || [ "$CLOUD_RUN_SERVICE_URL" == "YOUR_SERVICE_URL_HERE" ]; then
    echo "❌ ERROR: Please set CLOUD_RUN_SERVICE_URL in the script."
    exit 1
fi

if [ -z "$SERVICE_ACCOUNT_EMAIL" ]; then
    echo "❌ ERROR: Please set SERVICE_ACCOUNT_EMAIL in the script."
    exit 1
fi

echo "🚀 Deploying Backend to Google Cloud Run..."
echo "📍 Project: $PROJECT_ID"
echo "⚙️  Service: $SERVICE_NAME"

# Build & deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --source=$DOCKERFILE_PATH \
  --platform=managed \
  --region=$REGION \
  --allow-unauthenticated \
  --project=$PROJECT_ID \
  --memory=1Gi \
  --timeout=30m \
  --set-secrets=TAVILY_API_KEY=TAVILY_API_KEY:latest \
  --set-secrets=SCRAPECREATORS_API_KEY=SCRAPECREATORS_API_KEY:latest \
  --set-secrets=GOOGLE_API_KEY=GOOGLE_API_KEY:latest \
  --set-env-vars=GOOGLE_CLOUD_PROJECT=$PROJECT_ID \
  --set-env-vars=CLOUD_RUN_SERVICE_URL=$CLOUD_RUN_SERVICE_URL \
  --set-env-vars=SERVICE_ACCOUNT_EMAIL=$SERVICE_ACCOUNT_EMAIL

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Backend deployment successful!"
    echo "🔗 URL: $(gcloud run services describe $SERVICE_NAME --platform=managed --region=$REGION --format='value(status.url)')"
else
    echo "❌ Backend deployment failed"
    exit 1
fi