from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore
from pydantic import BaseModel
import random
import logging
import os
import json
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://rlgradleld.web.app",
        "https://rlgradleld.firebaseapp.com", 
        "http://localhost:5000",
        "http://localhost:3000",
        "*"  # Fallback for development
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

def get_db():
    try:
        return firestore.Client()  # Create client when needed
    except Exception as e:
        logger.error(f"Failed to create Firestore client: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

# Define the action space
def generate_random_action():
    return {
        "max_workers": random.randint(1, 4),
        "gradle_heap_gb": random.randint(3, 8),
        "kotlin_heap_gb": random.randint(3, 8)
    }

def action_to_key(action: dict) -> str:
    """Convert action dict to a string key for Q-learning"""
    return f"{action['max_workers']}_{action['gradle_heap_gb']}_{action['kotlin_heap_gb']}"

def get_best_action(q_table: Dict[str, float], exploration_rate: float = 0.1) -> dict:
    """Get the best action from Q-table with exploration"""
    if random.random() < exploration_rate or not q_table:
        # Explore: generate random action
        return generate_random_action()
    
    # Exploit: choose best action
    best_key = max(q_table.keys(), key=lambda k: q_table[k])
    max_workers, gradle_heap, kotlin_heap = best_key.split('_')
    return {
        "max_workers": int(max_workers),
        "gradle_heap_gb": int(gradle_heap),
        "kotlin_heap_gb": int(kotlin_heap)
    }

def get_best_action_from_q_table(q_table: Dict[str, float]) -> dict:
    """Get the best action from Q-table (highest Q-value)"""
    if not q_table:
        return generate_random_action()
    
    best_key = max(q_table.keys(), key=lambda k: q_table[k])
    # Convert key back to action dict
    parts = best_key.split('_')
    return {
        "max_workers": int(parts[0]),
        "gradle_heap_gb": int(parts[1]),
        "kotlin_heap_gb": int(parts[2])
    }

def calculate_reward(build_time: float, gradle_gc_time: float, kotlin_gc_time: float, kotlin_compile_duration: Optional[float] = None) -> float:
    """
    Calculate reward based on build time, Gradle GC time, and Kotlin GC time.
    Build time has more importance (60%), Gradle GC (25%), Kotlin GC (15%).
    Lower times = higher rewards.
    
    Args:
        build_time: Build time in milliseconds
        gradle_gc_time: Gradle GC time (normalized value)
        kotlin_gc_time: Kotlin GC time (normalized value)
        kotlin_compile_duration: Kotlin compile duration in milliseconds (optional)
    """
    # Convert build_time from milliseconds to seconds for normalization
    build_time_seconds = build_time / 1000.0
    
    # Normalize times (assuming reasonable ranges)
    # Build time: 0-300 seconds (5 minutes max)
    # GC times: 0-30 seconds each
    normalized_build_time = max(0, min(1, build_time_seconds / 300))
    normalized_gradle_gc = max(0, min(1, gradle_gc_time / 30))
    normalized_kotlin_gc = max(0, min(1, kotlin_gc_time / 30))
    
    # Calculate reward (lower times = higher rewards)
    build_reward = 1.0 - normalized_build_time  # 60% weight
    gradle_gc_reward = 1.0 - normalized_gradle_gc  # 25% weight
    kotlin_gc_reward = 1.0 - normalized_kotlin_gc  # 15% weight
    
    # Weighted sum
    total_reward = (0.6 * build_reward + 
                   0.25 * gradle_gc_reward + 
                   0.15 * kotlin_gc_reward)
    
    return max(0, min(1, total_reward))  # Ensure reward is between 0 and 1

def update_q_table(q_table: Dict[str, float], action: dict, reward: float, learning_rate: float = 0.1) -> Dict[str, float]:
    """Update Q-table with new reward"""
    action_key = action_to_key(action)
    if action_key not in q_table:
        q_table[action_key] = 0.0
    
    # Simple Q-learning update
    q_table[action_key] = q_table[action_key] + learning_rate * (reward - q_table[action_key])
    return q_table

class ActionRequest(BaseModel):
    experiment_id: str

class FeedbackRequest(BaseModel):
    experiment_id: str
    build_time: Optional[float] = None           # From GitHub Actions (in ms)
    gradle_gc_time: Optional[float] = None       # From GitHub Actions
    kotlin_gc_time: Optional[float] = None       # From GitHub Actions
    kotlin_compile_duration: Optional[float] = None  # From GitHub Actions (in ms)
    state: Optional[dict] = None

@app.get("/health")
async def health_check():
    """Health check endpoint for debugging"""
    return {
        "status": "healthy",
        "service": "rl-agent",
        "environment": os.getenv("ENVIRONMENT", "production")
    }

@app.options("/{path:path}")
async def options_handler(path: str):
    """Handle OPTIONS requests for CORS preflight"""
    return {"message": "OK"}

@app.post("/get-action")
async def get_action(req: ActionRequest):
    try:
        logger.info(f"Received action request for experiment: {req.experiment_id}")
        
        db = get_db()
        doc_ref = db.collection("experiments").document(req.experiment_id)
        
        # Check if we already generated an action for this experiment
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if data.get("last_action") and data.get("status") == "running":
                logger.info(f"Returning existing action for experiment: {req.experiment_id}")
                return data["last_action"]
        
        # Get Q-table for this experiment
        q_table = {}
        if doc.exists:
            data = doc.to_dict()
            q_table_str = data.get("q_table", "{}")
            try:
                q_table = json.loads(q_table_str)
            except json.JSONDecodeError:
                q_table = {}
        
        # Generate new action using RL
        action = get_best_action(q_table)
        
        logger.info(f"Generated new action: {action}")
        
        # Store the action and Q-table in Firestore
        doc_ref.set({
            "last_action": action,
            "status": "running",
            "q_table": json.dumps(q_table)
        }, merge=True)
        
        logger.info(f"Successfully stored action for experiment: {req.experiment_id}")
        return action
        
    except Exception as e:
        logger.error(f"Error in get_action: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/send-feedback")
async def send_feedback(req: FeedbackRequest):
    try:
        logger.info(f"Received feedback for experiment: {req.experiment_id}")
        logger.info(f"Build time: {req.build_time}ms, Gradle GC: {req.gradle_gc_time}, Kotlin GC: {req.kotlin_gc_time}, Kotlin compile: {req.kotlin_compile_duration}ms")
        
        # Validate that required metrics are provided
        if req.build_time is None or req.gradle_gc_time is None or req.kotlin_gc_time is None:
            raise HTTPException(status_code=400, detail="Missing required metrics: build_time, gradle_gc_time, kotlin_gc_time")
        
        # Calculate reward based on the metrics
        reward = calculate_reward(req.build_time, req.gradle_gc_time, req.kotlin_gc_time, req.kotlin_compile_duration)
        logger.info(f"Calculated reward: {reward}")
        
        db = get_db()
        doc_ref = db.collection("experiments").document(req.experiment_id)
        
        # Get current Q-table and last action
        doc = doc_ref.get()
        q_table = {}
        last_action = None
        
        if doc.exists:
            data = doc.to_dict()
            q_table_str = data.get("q_table", "{}")
            try:
                q_table = json.loads(q_table_str)
            except json.JSONDecodeError:
                q_table = {}
            last_action = data.get("last_action")
        
        # Update Q-table with the reward
        if last_action:
            q_table = update_q_table(q_table, last_action, reward)
            logger.info(f"Updated Q-table with reward {reward} for action {last_action}")
        
        # Get the best action from the updated Q-table
        best_action = get_best_action_from_q_table(q_table)
        logger.info(f"Best action from Q-table: {best_action}")
        
        # Store the feedback and updated Q-table
        doc_ref.set({
            "build_time": req.build_time,
            "gradle_gc_time": req.gradle_gc_time,
            "kotlin_gc_time": req.kotlin_gc_time,
            "kotlin_compile_duration": req.kotlin_compile_duration,
            "calculated_reward": reward,
            "state": req.state or {},
            "status": "completed",
            "q_table": json.dumps(q_table)
        }, merge=True)
        
        logger.info(f"Successfully stored feedback for experiment: {req.experiment_id}")
        return {
            "message": "Feedback received successfully",
            "calculated_reward": reward,
            "best_action": best_action,
            "metrics": {
                "build_time": req.build_time,
                "gradle_gc_time": req.gradle_gc_time,
                "kotlin_gc_time": req.kotlin_gc_time,
                "kotlin_compile_duration": req.kotlin_compile_duration
            }
        }
        
    except Exception as e:
        logger.error(f"Error in send_feedback: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/experiment/{experiment_id}/q-table")
async def get_q_table(experiment_id: str):
    """Get the Q-table for debugging"""
    try:
        db = get_db()
        doc_ref = db.collection("experiments").document(experiment_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return {"q_table": {}, "message": "Experiment not found"}
        
        data = doc.to_dict()
        q_table_str = data.get("q_table", "{}")
        try:
            q_table = json.loads(q_table_str)
        except json.JSONDecodeError:
            q_table = {}
        
        return {"q_table": q_table, "experiment_id": experiment_id}
        
    except Exception as e:
        logger.error(f"Error getting Q-table: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/experiment/{experiment_id}/metrics")
async def get_experiment_metrics(experiment_id: str):
    """Get experiment metrics and history"""
    try:
        db = get_db()
        doc_ref = db.collection("experiments").document(experiment_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return {"message": "Experiment not found"}
        
        data = doc.to_dict()
        return {
            "experiment_id": experiment_id,
            "last_action": data.get("last_action"),
            "status": data.get("status"),
            "build_time": data.get("build_time"),
            "gradle_gc_time": data.get("gradle_gc_time"),
            "kotlin_gc_time": data.get("kotlin_gc_time"),
            "kotlin_compile_duration": data.get("kotlin_compile_duration"),
            "calculated_reward": data.get("calculated_reward"),
            "state": data.get("state", {})
        }
        
    except Exception as e:
        logger.error(f"Error getting experiment metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
