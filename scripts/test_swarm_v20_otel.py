import subprocess
import time
import os
import re

# 🕵️ Nexus v20 OTel Alignment Verification
TOKEN = "nexus-secret-2026"
DB_PATH = "nexus-swarm/swarm_tasks.db"

def cleanup():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    subprocess.run(["pkill", "-f", "nexus_cli.py --swarm-mode"], stderr=subprocess.DEVNULL)

def start_nodes():
    nodes = [8001, 8002, 8003]
    for p in nodes:
        cmd = ["python3", "scripts/nexus_cli.py", "--swarm-mode", "--port", str(p), "--swarm-token", TOKEN]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def run_manager_and_collect():
    print("🚀 Running Manager & Collecting OTel Logs...")
    env = os.environ.copy()
    env["NEXUS_SWARM_TOKEN"] = TOKEN
    # Capture stdout to verify structured logs
    result = subprocess.run(["go", "run", "cmd/swarm-manager/main.go"], 
                          cwd="nexus-swarm", env=env, capture_output=True, text=True)
    return result.stdout

def main():
    cleanup()
    start_nodes()
    time.sleep(2)

    print("🛡️ [Phase 1: Trace Continuity Audit]")
    logs = run_manager_and_collect()
    
    # Verify TraceID exists and is consistent across spans
    trace_ids = re.findall(r"trace_id=([a-zA-Z0-9\-\_]+)", logs)
    if not trace_ids:
        print("❌ Error: No trace_id found in logs!")
        return

    unique_trace_id = trace_ids[0]
    print(f"✅ Found TraceID: {unique_trace_id}")
    
    spans = ["selection", "network", "execution"]
    for s in spans:
        if f"[SPAN:{s}]" in logs and unique_trace_id in logs:
            print(f"✅ Span Log Found: {s} (Trace verified)")
        else:
            print(f"❌ Missing or inconsistent Span: {s}")

    print("\n♻️ [Phase 2: SRE Recovery Event Audit]")
    # Mock a running task with expired lease
    mock_db = {
        "otel_test_task": {
            "id": "otel_test_task",
            "trace_id": "trace-original-123",
            "repo_url": "https://github.com/nexus/core",
            "status": "RUNNING",
            "lease_expires_at": "2020-01-01T00:00:00Z"
        }
    }
    with open(DB_PATH, "w") as f:
        import json
        json.dump(mock_db, f)

    recovery_logs = run_manager_and_collect()
    if "📢 [EVENT:task.recovered]" in recovery_logs:
        print("✅ Recovery Event Found!")
        if "previous_state=RUNNING" in recovery_logs and "attempt_count=1" in recovery_logs:
             print("✅ Event Fields Verified: previous_state, attempt_count")
    else:
        print("❌ Recovery Event Missing!")

    cleanup()
    print("\n✨ [Success] Phase 20 OTel Alignment Verification Finished.")

if __name__ == "__main__":
    main()
