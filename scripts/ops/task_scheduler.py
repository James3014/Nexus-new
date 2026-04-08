import os
import time
import subprocess
import logging
import json
from datetime import datetime

# Path Configuration
REPO_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[2])
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts/ops")
STATUS_FILE = os.path.join(REPO_ROOT, ".nexus/task_scheduler_status.json")
LOG_FILE = os.path.join(REPO_ROOT, ".nexus/task_scheduler.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def run_command(cmd, cwd=REPO_ROOT):
    logging.info(f"Executing: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            logging.error(f"Command failed (RC={result.returncode}): {result.stderr}")
        return result.returncode, result.stdout
    except Exception as e:
        logging.error(f"Exception during command execution: {str(e)}")
        return -1, str(e)

def update_status(state, loop_count):
    status = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "state": state,
        "loop_count": loop_count,
        "pid": os.getpid()
    }
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)

def main():
    import sys
    is_once = "--once" in sys.argv or "--dry-run" in sys.argv
    print(f"🚀 [Nexus-Scheduler] Starting {'Dry-Run' if is_once else 'Autonomous Daemon'}...")
    logging.info(f"Nexus Scheduler Starting (once={is_once})...")
    loop_count = 0
    
    while True:
        loop_count += 1
        print(f"🔄 [Round {loop_count}] Synchronizing INDEX to Manifest...")
        update_status("SYNCING", loop_count)
        
        # 1. Sync INDEX.md to task_manifest.yaml
        rc, out = run_command("uv run scripts/ops/index_to_manifest.py")
        if rc != 0:
            print("  [!] Index Sync Failed.")
            if is_once: sys.exit(1)
            time.sleep(30)
            continue
            
        # 2. Start Orchestrator (ERA-C Batch)
        print("  [EXEC] Launching Orchestrator (Multi-Worker Path)...")
        update_status("EXECUTING", loop_count)
        if is_once:
             print("  [Dry-Run] Skipping orchestrator execution.")
        else:
             rc, out = run_command("scripts/ops/nexus_orchestrator.sh")
        
        # 3. Final Gate & Live Status Update
        print("  [GATE] Performing Final Integrity Check and Index Sync...")
        update_status("GATING", loop_count)
        if not is_once:
            run_command("uv run scripts/ops/ci_gate.py")
        run_command("uv run python scripts/ops/post_index_update.py")
        
        print(f"✅ [Round {loop_count}] Batch completed.")
        update_status("IDLE", loop_count)
        
        if is_once:
            print("🏁 [Nexus-Scheduler] Dry-Run/Once-off completed. Exiting.")
            sys.exit(0)
            
        # Pulse Interval
        time.sleep(60)

if __name__ == "__main__":
    main()
