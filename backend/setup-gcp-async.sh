#!/bin/bash

# --- Configuration ---
# (These should match your existing deploy script)
PROJECT_ID="gen-lang-client-0048564118"
SERVICE_NAME="company-researcher"
REGION="us-central1"
QUEUE_ID="research-jobs-queue"

# This is your service account email (from logs/IAM)
SERVICE_ACCOUNT_EMAIL="373126702591-compute@developer.gserviceaccount.com"

echo "🚀 Provisioning Google Cloud resources for async research..."
echo "📍 Project: $PROJECT_ID"
echo "🔩 Service Account: $SERVICE_ACCOUNT_EMAIL"

# --- 1. Enable APIs ---
echo "⚙️  Enabling required APIs..."
gcloud services enable \
  firestore.googleapis.com \
  cloudtasks.googleapis.com \
  run.googleapis.com \
  iam.googleapis.com \
  --project=$PROJECT_ID

# --- 2. Create Firestore Database ---
# (This command will fail if one already exists, which is fine)
echo "⚙️  Creating Firestore database in $REGION..."
gcloud firestore databases create --location=$REGION --project=$PROJECT_ID

# --- 3. Create Cloud Tasks Queue ---
echo "⚙️  Creating Cloud Tasks queue: $QUEUE_ID..."
gcloud tasks queues create $QUEUE_ID --location=$REGION --project=$PROJECT_ID

# --- 4. Set IAM Permissions for the Service Account ---
echo "🔐 Assigning permissions to $SERVICE_ACCOUNT_EMAIL..."

# Role: Cloud Datastore User (to read/write from/to Firestore)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/datastore.user"

# Role: Cloud Tasks Enqueuer (to create new tasks)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/cloudtasks.enqueuer"

# Role: Service Account Token Creator (for creating auth tokens for tasks)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/iam.serviceAccountTokenCreator"

# Role: Cloud Run Invoker (so Cloud Tasks can call the /run-research-job endpoint)
gcloud run services add-iam-policy-binding $SERVICE_NAME \
  --region=$REGION \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/run.invoker" \
  --project=$PROJECT_ID

echo "✅ All resources provisioned successfully."
echo "🔔  Reminder: You must manually set Firestore Security Rules in the GCP Console."