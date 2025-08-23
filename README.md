# 🚀 RL Gradle Learning Days

A Reinforcement Learning (RL) system that optimizes Gradle build configurations by automatically adjusting parallel workers, JVM heap sizes.

Website Demo:  
https://rlgradleld.web.app/
Article: https://dev.to/cdsap/gradle-learning-day-reinforcement-learning-for-build-optimization-2oh7


## 🏗️ Architecture

The system consists of:
- **RL Agent**: Python FastAPI service running on Google Cloud Run
- **Firebase Functions**: Serverless functions for experiment management
- **Firebase Hosting**: Web dashboard for monitoring experiments
- **GitHub Actions**: CI/CD pipeline for running experiments
- **Firestore**: Database for storing experiment data



## 🛠️ Setup Instructions

### 1. Prerequisites
- Google Cloud Platform account
- Firebase project
- GitHub repository
- Node.js and Python 3.11+

### 2. Configuration
```bash
# Copy configuration templates
cp env.example .env
cp config.example.js config.js

# Edit with your actual values
nano .env
nano config.js
```

### 3. Required Environment Variables
```bash
# Firebase
FIREBASE_PROJECT_ID=your-actual-project-id
FIREBASE_REGION=us-central1

# Cloud Run URLs
RL_AGENT_URL=https://your-rl-agent-url.run.app
TRIGGER_EXPERIMENT_URL=https://your-trigger-experiment-url.run.app

# Firebase Functions
FIREBASE_FUNCTIONS_BASE_URL=https://your-project.your-region.cloudfunctions.net
```

### 4. Deploy Services
```bash
# Deploy RL Agent
cd agent
./deploy-agent.sh

# Deploy Firebase Functions
firebase deploy --only functions

# Deploy Web Dashboard
firebase deploy --only hosting
```

## 📁 Repository Structure

```
├── agent/                 # RL Agent (Python FastAPI)
├── functions/            # Firebase Cloud Functions
├── public/              # Web Dashboard
├── .github/workflows/   # GitHub Actions
├── config.example.js    # Configuration template
├── env.example         # Environment variables template
└── README.md           # This file
```

## 🔧 Configuration Setup

### For Local Development
1. **Keep `public/config.js`** with your real URLs (this file is gitignored)
2. **Keep `public/index.html`** with your real URLs (this file is gitignored)
3. Your local deployment will work automatically

### For GitHub Publication
1. **Replace `public/config.js`** with `public/config.template.js`:
   ```bash
   cp public/config.template.js public/config.js
   ```
2. **Update the placeholder values** in `public/config.js` with your actual URLs
3. **Commit and push** to GitHub

### Files to Manage
- ✅ **Keep in repo**: `public/config.template.js` (template with placeholders)
- ✅ **Keep in repo**: `public/index.html` (now safe with config-based URLs)
- ❌ **Exclude from repo**: `public/config.js` (your real working config)


## 🚀 Usage

1. **Start Experiment**: Use the web dashboard to configure and start RL experiments
2. **Monitor Progress**: Track experiment status and performance metrics
3. **View Results**: Analyze charts showing build performance vs. configurations
4. **Learn**: The system automatically improves configurations using Q-learning

