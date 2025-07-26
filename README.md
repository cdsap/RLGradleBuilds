# RLGradleBuilds 🚀

A **Reinforcement Learning (RL) system for optimizing Gradle build parameters** using a continuous learning loop with Firebase Functions and GitHub Actions.

## 🎯 Overview

This system automatically optimizes Gradle build performance by:
- Using a Q-learning RL agent to generate optimal build parameters
- Running experiments on target repositories with different configurations
- Collecting performance metrics and feeding them back to improve the model
- Continuously iterating to find the best build settings

## 🏗️ Architecture

### Core Components

**1. Firebase Functions (`functions/`)**
- `triggerExperiment`: Creates experiments and triggers GitHub Actions
- `updateExperimentStatusData`: Receives metrics and orchestrates the continuous learning loop
- `getAllExperiments`: API for the UI to fetch experiment data
- `getExperimentData`: Gets individual experiment details

**2. RL Agent (`agent/`)**
- Python FastAPI application deployed to Cloud Run
- Implements Q-learning algorithm for parameter optimization
- Endpoints: `/get-action` (generates parameters) and `/send-feedback` (receives metrics)
- Optimizes: `max_workers`, `gradle_heap_gb`, `kotlin_heap_gb`

**3. GitHub Actions Workflow (`.github/workflows/`)**
- `run.yaml`: Main workflow that orchestrates the build process
- `seed/action.yaml`: Initial build with RL-optimized parameters
- `run/action.yaml`: Main experiment execution
- `report/action.yaml`: Collects metrics and sends feedback

**4. Frontend UI (`public/`)**
- Dashboard to trigger and monitor experiments
- Shows experiment status, iterations, best actions, and performance metrics
- Real-time updates of experiment progress

## 🔄 Continuous Learning Flow

1. **Experiment Creation**: User triggers experiment via UI
2. **RL Action Generation**: Agent generates optimal build parameters
3. **GitHub Actions Execution**: Runs build with RL parameters on target repository
4. **Metrics Collection**: Gathers build time, GC times, compile duration
5. **Feedback Loop**: Sends metrics to RL agent for Q-table updates
6. **Next Iteration**: Automatically schedules next experiment with improved parameters
7. **Convergence**: Repeats until optimal parameters are found (max 10 iterations)

## 🛠️ Technology Stack

- **Backend**: Firebase Functions (Node.js), Cloud Run (Python)
- **Frontend**: HTML/CSS/JavaScript with Firebase Hosting
- **CI/CD**: GitHub Actions with dynamic parameter injection
- **Database**: Firestore for experiment data and Q-tables
- **ML**: Q-learning reinforcement learning algorithm
- **Build System**: Gradle with dynamic property optimization

## 📊 Optimization Targets

- **Build Performance**: Faster compilation times
- **Memory Usage**: Optimal heap sizes for Gradle and Kotlin daemons
- **Parallelization**: Optimal number of worker threads
- **Resource Efficiency**: Balanced CPU and memory utilization

## 🚀 Quick Start

### Prerequisites
- Google Cloud Platform account
- Firebase project
- GitHub repository with GitHub Actions enabled

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/cdsap/RLGradleBuilds.git
   cd RLGradleBuilds
   ```

2. **Deploy the RL Agent**
   ```bash
   cd agent
   ./deploy-agent.sh
   ```

3. **Deploy Firebase Functions**
   ```bash
   ./deploy-firebase.sh
   ```

4. **Set up environment variables**
   - Set `GITHUB_TOKEN` in Firebase Functions
   - Configure `RL_AGENT_URL` if needed

5. **Access the UI**
   - Deploy to Firebase Hosting or run locally
   - Navigate to the dashboard to start experiments

## 📁 Project Structure

```
RLGradleBuilds/
├── agent/                    # RL Agent (Python FastAPI)
│   ├── main.py              # FastAPI application
│   ├── Dockerfile           # Container configuration
│   ├── requirements.txt     # Python dependencies
│   └── deploy-agent.sh      # Deployment script
├── functions/               # Firebase Functions
│   ├── index.js            # Main function logic
│   ├── package.json        # Node.js dependencies
│   └── package-lock.json
├── .github/workflows/       # GitHub Actions
│   ├── run.yaml            # Main workflow
│   ├── seed/               # Seed build action
│   ├── run/                # Main execution action
│   └── report/             # Metrics collection action
├── public/                 # Frontend UI
│   └── index.html          # Dashboard
├── deploy-firebase.sh      # Firebase deployment script
└── README.md              # This file
```

## 🔧 Configuration

### RL Agent Parameters
The agent optimizes these Gradle build parameters:
- `max_workers`: Number of parallel worker threads
- `gradle_heap_gb`: Gradle JVM heap size in GB
- `kotlin_heap_gb`: Kotlin daemon heap size in GB

