#!/bin/bash

# Configuration
PROJECT_ID="gen-lang-client-0048564118"
SERVICE_NAME="company-researcher"
REGION="us-central1" # <-- Or your preferred region
DOCKERFILE_PATH="." # Dockerfile is in the current (backend) folder

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
  --set-secrets=TAVILY_API_KEY=TAVILY_API_KEY:latest \
  --set-secrets=SCRAPECREATORS_API_KEY=SCRAPECREATORS_API_KEY:latest \
  --set-secrets=GOOGLE_API_KEY=GOOGLE_API_KEY:latest

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Backend deployment successful!"
    echo "🔗 URL: $(gcloud run services describe $SERVICE_NAME --platform=managed --region=$REGION --format='value(status.url)')"
    echo ""
    echo "📝 Next step:"
    echo "1. Copy this URL."
    echo "2. Update frontend/src/App.jsx and backend/app.py."
else
    echo "❌ Backend deployment failed"
    exit 1
fi