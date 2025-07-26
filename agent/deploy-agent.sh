#!/bin/bash

set -e

echo "🚀 Deploying RL Agent to Cloud Run..."

# Configuration
PROJECT_ID="rlgradleld"
REGION="us-central1"
SERVICE_NAME="rl-agent"
IMAGE_NAME="$REGION-docker.pkg.dev/$PROJECT_ID/$SERVICE_NAME/$SERVICE_NAME"

echo "📋 Configuration:"
echo "  Project ID: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Service Name: $SERVICE_NAME"
echo "  Image Name: $IMAGE_NAME"
echo ""

# Create Artifact Registry repository if it doesn't exist
echo "🏗️ Creating Artifact Registry repository..."
gcloud artifacts repositories create rl-agent \
  --repository-format=docker \
  --location=$REGION \
  --project=$PROJECT_ID \
  --quiet || echo "Repository already exists"

# Build and push using gcloud build
echo "📦 Building and pushing Docker image with gcloud build..."
gcloud builds submit --tag $IMAGE_NAME .

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --project $PROJECT_ID \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --max-instances 10

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --project=$PROJECT_ID --format="value(status.url)")

echo ""
echo "✅ RL Agent deployed successfully!"
echo "🌐 Service URL: $SERVICE_URL"
echo ""
echo "🧪 Test the deployment:"
echo "  curl $SERVICE_URL/health"
echo ""
echo "📋 Next steps:"
echo "1. Update Firebase Functions with RL_AGENT_URL=$SERVICE_URL"
echo "2. Deploy Firebase Functions"
echo "3. Start an experiment!" 