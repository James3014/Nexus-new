import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def trigger_learning_loop(mode="async"):
    """🚀 Nexus Post-Run Hook: Trigger autonomous brain crystallization."""
    cmd = ["uv", "run", "python", "scripts/ops/brain_loop_closure.py", f"--mode={mode}"]
    try:
        # Non-blocking child process to ensure experimental flow continues
        subprocess.Popen(cmd, env=os.environ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        # Log failure to telemetry for manual re-drive
        with open(".nexus/metrics/learning_failure.jsonl", "a") as f:
            import json
            f.write(json.dumps({"ts": time.time(), "error": str(e), "mode": mode}) + "\n")

def swarm_task(i):
    task_name = f"swarm_unit_{i:03d}"
    cmd = [
        "uv", "run", "python", "-c", 
        f"from scripts.nightshift import AutoResearchNightShift; ns = AutoResearchNightShift('{task_name}', max_rounds=2, budget_min=1); ns.run()"
    ]
    env = {**os.environ, "NEXUS_SKIP_PROTOCOL_GATE": "1"}
    
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
        # 🧪 Nexus Flush Buffer
        time.sleep(2)
        
        if result.returncode == 0:
            # 🏁 Trigger per-task learning
            trigger_learning_loop(mode="async")
            return f"✅ {task_name} | PASS"
        else:
            return f"❌ {task_name} | FAIL"
    except Exception:
        return f"🔥 {task_name} | CRASH"

def main():
    concurrency = 100
    print(f"🐝 [Nexus-Swarm] Launching {concurrency} parallel logic-units...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(swarm_task, i): i for i in range(concurrency)}
        for future in as_completed(futures):
            print(future.result())
    
    # 🏆 Total Batch Completion: Final full-sweep crystallization
    print("🏁 Swarm batch ended. Triggering final batch closure...")
    trigger_learning_loop(mode="batch")

if __name__ == "__main__":
    main()
