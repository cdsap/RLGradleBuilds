import os
import logging
import json
import random
import math
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from firebase_admin import firestore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv('FIREBASE_HOSTING_URL', 'http://localhost:3000'),
        os.getenv('FIREBASE_HOSTING_ALT_URL', 'http://localhost:5000')
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Type"]
)

def get_db():
    try:
        return firestore.Client()  # Create client when needed
    except Exception as e:
        logger.error(f"Failed to create Firestore client: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

# Define the action space
def generate_random_action(experiment_id: str = None) -> dict:
    """Generate a random action with different parameters"""
    # Create a unique seed based on experiment_id and current time
    if experiment_id:
        # Use experiment_id hash + current time for better randomness
        seed_value = hash(experiment_id) + int(time.time() * 1000)
        random.seed(seed_value)
    else:
        # Fallback to current time
        random.seed(int(time.time() * 1000))
    
    max_workers = random.randint(1, 4)
    gradle_heap_gb = random.randint(2, 8)
    kotlin_heap_gb = random.randint(2, 8)
    
    return {
        "max_workers": max_workers,
        "gradle_heap_gb": gradle_heap_gb,
        "kotlin_heap_gb": kotlin_heap_gb
    }

def action_to_key(action: dict) -> str:
    """Convert action dict to a string key for Q-learning"""
    return f"{action['max_workers']}_{action['gradle_heap_gb']}_{action['kotlin_heap_gb']}"

def get_best_action(q_table: Dict[str, float], exploration_rate: float = None, used_actions: set = None, experiment_id: str = None, current_iteration: int = 1) -> dict:
    """Get the best action from Q-table with adaptive exploration and strict duplicate prevention"""
    if used_actions is None:
        used_actions = set()
    
    # Calculate adaptive exploration rate based on iteration
    if exploration_rate is None:
        # Start with 90% exploration, decrease to 20% by iteration 15
        exploration_rate = max(0.2, 0.9 - (current_iteration - 1) * 0.05)
        logger.info(f"Adaptive exploration rate: {exploration_rate:.2f} for iteration {current_iteration}")
    
    # If Q-table is empty or very small, always explore
    if len(q_table) < 3:
        action = generate_random_action(experiment_id)
        action_key = action_to_key(action)
        attempts = 0
        # Try harder to avoid duplicates (up to 50 attempts)
        while action_key in used_actions and attempts < 50:
            action = generate_random_action(experiment_id)
            action_key = action_to_key(action)
            attempts += 1
        logger.info(f"Generated action after {attempts} attempts: {action}")
        return action
    
    # If we have some data, use adaptive exploration rate
    if random.random() < exploration_rate:
        # Explore: generate random action
        action = generate_random_action(experiment_id)
        action_key = action_to_key(action)
        attempts = 0
        # Try harder to avoid duplicates (up to 50 attempts)
        while action_key in used_actions and attempts < 50:
            action = generate_random_action(experiment_id)
            action_key = action_to_key(action)
            attempts += 1
        logger.info(f"Explored action after {attempts} attempts: {action}")
        return action
    
    # Exploit: choose best action that hasn't been used
    best_actions = sorted(q_table.keys(), key=lambda k: q_table[k], reverse=True)
    
    for best_key in best_actions:
        if best_key not in used_actions:
            max_workers, gradle_heap, kotlin_heap = best_key.split('_')
            action = {
                "max_workers": int(max_workers),
                "gradle_heap_gb": int(gradle_heap),
                "kotlin_heap_gb": int(kotlin_heap)
            }
            logger.info(f"Exploiting best unused action: {action}")
            return action
    
    # If all best actions have been used, generate a new random action
    action = generate_random_action(experiment_id)
    action_key = action_to_key(action)
    attempts = 0
    while action_key in used_actions and attempts < 50:
        action = generate_random_action(experiment_id)
        action_key = action_to_key(action)
        attempts += 1
    logger.info(f"Generated fallback action after {attempts} attempts: {action}")
    return action

def get_best_action_from_actual_performance(variants: List[dict]) -> dict:
    """Get the best action based on actual performance (highest reward)"""
    if not variants:
        return generate_random_action()
    
    # Find the variant with the highest reward
    best_variant = max(variants, key=lambda v: v.get('reward', 0))
    
    if 'rl_action' in best_variant:
        return best_variant['rl_action']
    else:
        return generate_random_action()

def calculate_reward(build_time: float, gradle_gc_time: float, kotlin_gc_time: float, kotlin_compile_duration: Optional[float] = None) -> float:
    """
    Calculate reward using continuous logarithmic scale for maximum coverage.
    Build time (100%) - pure focus on overall build performance.
    GC times and Kotlin compile are kept for monitoring but excluded from reward calculation.
    Lower build times = higher rewards.
    
    This formula handles any build time range:
    - Ultra-fast builds (1ms) get near-perfect rewards
    - Very slow builds (hours) get low but differentiable rewards
    - No arbitrary thresholds or cliffs
    
    Args:
        build_time: Build time in milliseconds
        gradle_gc_time: Gradle GC time (normalized value) - kept for monitoring only
        kotlin_gc_time: Kotlin GC time (normalized value) - kept for monitoring only
        kotlin_compile_duration: Kotlin compile duration in milliseconds (optional) - kept for monitoring only
    """
    import math
    
    # Convert build_time from milliseconds to seconds for normalization
    build_time_seconds = build_time / 1000.0
    
    # Continuous logarithmic scale - no capping, handles any range
    # log10(1 + time) handles 0s builds gracefully and compresses wide ranges
    log_time = math.log10(1 + build_time_seconds)
    
    # Exponential decay that works for any build time
    # Divide by 2 to slow decay and provide better differentiation
    # This gives: 1s=0.86, 10s=0.59, 100s=0.37, 1000s=0.22, 10000s=0.14
    reward = math.exp(-log_time / 2)
    
    # Ensure reward is between 0.01 and 1.0
    # 0.01 minimum prevents zero rewards for extremely slow builds
    return max(0.01, min(1.0, reward))

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
        used_actions = set()
        variants = []  # Initialize variants outside the if block
        
        if doc.exists:
            data = doc.to_dict()
            q_table_str = data.get("q_table", "{}")
            try:
                q_table = json.loads(q_table_str)
            except json.JSONDecodeError:
                q_table = {}
            
            # Get used actions from variants
            variants = data.get("variants", [])
            for variant in variants:
                if "rl_action" in variant:
                    action_key = action_to_key(variant["rl_action"])
                    used_actions.add(action_key)
            
            logger.info(f"Used actions for experiment {req.experiment_id}: {used_actions}")
            logger.info(f"Total variants: {len(variants)}, Unique actions: {len(used_actions)}")
        
        # Calculate current iteration based on variants
        current_iteration = len(variants) + 1
        
        # Generate new action using RL with adaptive exploration
        action = get_best_action(q_table, used_actions=used_actions, experiment_id=req.experiment_id, current_iteration=current_iteration)
        
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
        logger.info(f"GC times monitored (not used in reward): Gradle GC: {req.gradle_gc_time}s, Kotlin GC: {req.kotlin_gc_time}s")
        logger.info(f"Reward based on: Build time: {req.build_time}ms (Kotlin compile monitored but not used in reward)")
        
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
        
        # Get current variants to check iterations and determine best action
        variants = data.get("variants", [])
        
        # Always get the best action from actual performance for final result
        best_action = get_best_action_from_actual_performance(variants)
        logger.info(f"Best action from actual performance: {best_action}")
        
        # Get maxIterations from environment variable or experiment data, default to 15
        maxIterations = int(os.getenv('MAX_ITERATIONS', '15'))
        if 'max_iterations' in data:
            maxIterations = int(data['max_iterations'])
        logger.info(f"Max iterations set to: {maxIterations}")
        
        # Store the feedback and updated Q-table
        doc_ref.set({
            "build_time": req.build_time,
            "gradle_gc_time": req.gradle_gc_time,
            "kotlin_gc_time": req.kotlin_gc_time,
            "kotlin_compile_duration": req.kotlin_compile_duration,
            "calculated_reward": reward,
            "state": req.state or {},
            "status": "running",  # Keep as running until max iterations reached
            "q_table": json.dumps(q_table)
        }, merge=True)
        
        # Check if we've reached max iterations AFTER storing the variant
        if len(variants) >= maxIterations:
            # Mark as completed
            await db.collection('experiments').doc(req.experiment_id).update({
                'status': 'completed',
                'final_message': f'Experiment completed after {len(variants)} iterations'
            })
            logger.info(f"Experiment {req.experiment_id} completed after {len(variants)} iterations")
            return {
                "message": f"Experiment completed after {len(variants)} iterations",
                "calculated_reward": reward,
                "best_action": best_action,
                "metrics": {
                    "build_time": req.build_time,
                    "gradle_gc_time": req.gradle_gc_time,
                    "kotlin_gc_time": req.kotlin_gc_time,
                    "kotlin_compile_duration": req.kotlin_compile_duration
                }
            }
        
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

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
