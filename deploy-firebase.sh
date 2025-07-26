#!/bin/bash

echo "🚀 Deploying Firebase Functions..."

# Navigate to functions directory
cd functions

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Deploy the functions
echo "🔥 Deploying Firebase functions..."
firebase deploy --only functions:triggerExperiment,functions:getExperimentData,functions:getAllExperiments,functions:updateExperimentStatusData

echo "✅ Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "1. Set the GITHUB_TOKEN environment variable in Firebase Functions"
echo "2. Test the UI at your Firebase hosting URL"
echo "3. Enter a repository name and start an experiment!" 