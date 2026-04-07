import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def swarm_task(i):
    task_name = f"swarm_unit_{i:03d}"
    cmd = [
        "uv", "run", "python", "-c", 
        f"from scripts.nightshift import AutoResearchNightShift; ns = AutoResearchNightShift('{task_name}', max_rounds=2, budget_min=1); ns.run()"
    ]
    env = {**os.environ, "NEXUS_SKIP_PROTOCOL_GATE": "1"}
    
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
        # 🧪 Nexus Flush Buffer: Give OS time to sync the hardware fsync call
        import time
        time.sleep(2)
        
        if result.returncode == 0:
            return f"✅ {task_name} | PASS"
        else:
            return f"❌ {task_name} | FAIL"
    except Exception:
        return f"🔥 {task_name} | CRASH"

def main():
    concurrency = 100
    print(f"🐝 [Nexus-Swarm] Launching {concurrency} parallel logic-units...")
    with ThreadPoolExecutor(max_workers=10) as executor: # 稍微降低 Workers 確保緩衝
        futures = {executor.submit(swarm_task, i): i for i in range(concurrency)}
        for future in as_completed(futures):
            print(future.result())

if __name__ == "__main__":
    main()
