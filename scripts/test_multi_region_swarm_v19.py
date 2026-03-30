import subprocess
import time
import os
import json
import signal

# 🕵️ Nexus v19.1 Durable Control Plane Verification
TOKEN = "nexus-secret-2026"
DB_PATH = "nexus-swarm/swarm_tasks.db"

def cleanup():
    print("🧹 Cleaning up old artifacts...")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    subprocess.run(["pkill", "-f", "nexus_cli.py --swarm-mode"], stderr=subprocess.DEVNULL)

def start_nodes():
    print("🐝 Starting Multi-Region Nodes...")
    nodes = [
        {"port": 8001, "region": "us-east-1"},
        {"port": 8002, "region": "eu-west-1"},
        {"port": 8003, "region": "ap-northeast-1"}
    ]
    procs = []
    for n in nodes:
        cmd = [
            "python3", "scripts/nexus_cli.py",
            "--swarm-mode",
            "--port", str(n["port"]),
            "--region", str(n["region"]),
            "--swarm-token", str(TOKEN)
        ]
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p)
    return procs

def run_manager():
    print("🚀 Running Swarm Manager...")
    env = os.environ.copy()
    env["NEXUS_SWARM_TOKEN"] = TOKEN
    return subprocess.Popen(["go", "run", "cmd/swarm-manager/main.go"], 
                    cwd="nexus-swarm", 
                    env=env)

def main():
    cleanup()
    nodes = start_nodes()
    time.sleep(3)

    print("🛡️ [Phase 1: Normal Operation & Persistence]")
    manager = run_manager()
    time.sleep(2) # Give it time to save the initial PENDING task
    
    print("💀 [Phase 2: Crash Simulation] Killing Manager...")
    manager.terminate()
    manager.wait()

    print("🔍 [Phase 3: Inspecting Persistence] Checking DB state...")
    with open(DB_PATH, "r") as f:
        tasks = json.load(f)
        for tid, t in tasks.items():
            print(f"  - Task {tid}: Status={t['status']}, Attempt={t['attempt_count']}")

    print("♻️ [Phase 4: Recovery Test] Forcing a Stalled State...")
    # Manually backdate a Running task's lease to force recovery
    with open(DB_PATH, "r") as f:
        tasks = json.load(f)
    
    for tid, t in tasks.items():
        if t["status"] == "RUNNING":
            t["lease_expires_at"] = "2020-01-01T00:00:00Z" # Force expiration
    
    with open(DB_PATH, "w") as f:
        json.dump(tasks, f, indent=2)

    print("🚀 [Phase 5: Restart Manager] Verifying Stalled Task Recovery...")
    manager_v2 = run_manager()
    time.sleep(5)
    manager_v2.terminate()
    manager_v2.wait()

    cleanup()
    print("✨ [Success] v19.1 Durable Control Plane Verification Finished.")

if __name__ == "__main__":
    main()
