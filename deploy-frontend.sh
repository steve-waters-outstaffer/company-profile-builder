#!/bin/bash

# Configuration
PROJECT_ID="gen-lang-client-0048564118"

echo "🚀 Deploying Frontend to Firebase Hosting..."
echo "📍 Project: $PROJECT_ID"

# 1. Build the React App
echo "⚙️  Running 'npm run build' in /frontend..."
cd frontend
npm run build
if [ $? -ne 0 ]; then
    echo "❌ Frontend build failed"
    cd ..
    exit 1
fi
cd ..

# 2. Deploy to Firebase
echo "🔥 Deploying to Firebase Hosting..."
firebase deploy --only hosting --project=$PROJECT_ID

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Frontend deployment successful!"
    echo "🔗 Hosting URL: https://$PROJECT_ID.web.app"
else
    echo "❌ Frontend deployment failed"
    exit 1
fi