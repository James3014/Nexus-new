import os
import subprocess
import json
import uuid
import logging
from typing import Dict, Any
from fastapi import FastAPI, BackgroundTasks, Request
from pydantic import BaseModel
from pathlib import Path

# 🛡️ Logging Configuration
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger("NEXUS-SHADOW")

app = FastAPI(title="Nexus Shadow Audit Webhook (v22)")

NEXUS_ROOT = Path("/Users/jameschen/Workspace/nexus")
QUEUE_FILE = NEXUS_ROOT / ".nexus" / "shadow" / "queue.json"

class PRPayload(BaseModel):
    pr_number: int
    repository: str
    branch: str
    author: str
    timestamp: str

def process_audit(pr_id: str):
    """Background Worker for Shadow Audit"""
    logger.info(f"🛡️ Starting Background Audit for PR {pr_id}...")
    calibrator_path = NEXUS_ROOT / "scripts" / "shadow" / "calibrator.py"
    try:
        # 🛡️ Call Calibrator as a background process
        subprocess.run(["python3", str(calibrator_path), pr_id], check=True)
        logger.info(f"✅ Background Audit for PR {pr_id} complete.")
    except Exception as e:
        logger.error(f"❌ Background Audit failed for PR {pr_id}: {e}")

@app.post("/shadow-audit")
async def shadow_audit(payload: PRPayload, background_tasks: BackgroundTasks):
    """Async PR Audit Gateway (Accept-and-Forget)"""
    pr_id = str(payload.pr_number)
    logger.info(f"🛡️ Received PR {pr_id} from {payload.author}. Queuing...")
    
    # 🛡️ Queue the task (append-only mock)
    # real queue logic would use redis/celery, but for v22 we use background_tasks
    background_tasks.add_task(process_audit, pr_id)
    
    return {
        "status": "accepted",
        "pr_id": pr_id,
        "message": "[NEXUS v22] Shadow Audit queued asynchronously. Fail-open protocol active."
    }

@app.get("/health")
async def health():
    return {"status": "ok", "mode": "distributed-v22"}

if __name__ == "__main__":
    import uvicorn
    # Listening on :8081 for Shadow Webhook (8080 Conflict Avoidance)
    uvicorn.run(app, host="0.0.0.0", port=8081)
