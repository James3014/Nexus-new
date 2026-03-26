import subprocess
import time
import os
import re
import json
import statistics

# ⚡️ Nexus NSP v21.1 Stress Test & Latency Audit
DB_PATH = "nexus-swarm/swarm_tasks.db"
TOKEN = "nexus-secret-2026"

def inject_tasks(count):
    print(f"📥 Injecting {count} Pending tasks into {DB_PATH}...")
    tasks = {}
    for i in range(count):
        task_id = f"stress-task-{i}"
        tasks[task_id] = {
            "id": task_id,
            "trace_id": "",
            "repo_url": "https://github.com/nexus/stress-test",
            "path": f"src/module_{i}.py",
            "status": "PENDING",
            "lease_expires_at": "0001-01-01T00:00:00Z",
            "attempt_count": 0
        }
    with open(DB_PATH, "w") as f:
        json.dump(tasks, f)

def run_manager_and_audit(duration_sec=30):
    print(f"🚀 Launching Swarm Manager for {duration_sec}s audit...")
    cmd = ["go", "run", "cmd/swarm-manager/main.go"]
    env = os.environ.copy()
    env["NEXUS_SWARM_TOKEN"] = TOKEN
    
    proc = subprocess.Popen(cmd, cwd="nexus-swarm", env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    start_time = time.time()
    logs = []
    
    try:
        while time.time() - start_time < duration_sec:
            line = proc.stdout.readline()
            if line:
                logs.append(line.strip())
            else:
                break
    finally:
        proc.terminate()

    return logs

def analyze_logs(logs, manager_region="us-east-1", baseline_tps=None, node_count=3):
    print(f"📊 Analyzing OTel Spans (Manager Region: {manager_region})...")
    
    selection_times = []
    
    # Segmented Latency lists
    local_net_times = []
    cross_net_times = []
    local_exec_times = []
    cross_exec_times = []
    
    task_done_count = 0

    # Parsing
    for line in logs:
        if "[SPAN:selection]" in line:
            m = re.search(r"duration_us=(\d+)", line)
            if m: selection_times.append(int(m.group(1)))
        elif "[SPAN:network]" in line:
            m_dur = re.search(r"duration_ms=(\d+)", line)
            m_to = re.search(r"to=([a-z0-9\-]+)", line)
            if m_dur and m_to:
                dur = int(m_dur.group(1))
                dest_region = m_to.group(1)
                if dest_region == manager_region:
                    local_net_times.append(dur)
                else:
                    cross_net_times.append(dur)
        elif "[SPAN:execution]" in line:
            m_dur = re.search(r"duration_ms=(\d+)", line)
            if m_dur:
                dur = int(m_dur.group(1))
                # Note: In this simple log, execution doesn't have the region, 
                # but we can infer from the preceding network span if we did more complex parsing.
                # For now, we'll just use overall execution but keep the lists for future logic.
                local_exec_times.append(dur)
                task_done_count += 1

    if not local_exec_times:
        print("❌ No tasks completed during the audit period.")
        return 0

    print(f"\n📈 --- Hardened Scaling Metrics (v22.1) ---")
    print(f"✅ Total Tasks Completed: {task_done_count}")
    
    tps = task_done_count / 20 # fixed audit duration
    print(f"🚀 Measured Throughput: {tps:.2f} Tasks/Sec")

    if baseline_tps and node_count > 3:
        efficiency = tps / (baseline_tps * (node_count / 3))
        print(f"⚖️  Scaling Efficiency (N={node_count}): {efficiency:.2%}")

    def report_stat(name, data, unit):
        if not data: return
        p50 = statistics.median(data)
        p95 = statistics.quantiles(data, n=20)[18] if len(data) >= 20 else max(data)
        print(f"🔹 {name}: P50={p50:.2f}{unit}, P95={p95:.2f}{unit}")

    report_stat("Selection Latency", selection_times, "us")
    report_stat("Local Network (Intra-Region)", local_net_times, "ms")
    report_stat("Cross-Region Network (Inter-Region)", cross_net_times, "ms")
    report_stat("Execution Time (Overall)", local_exec_times, "ms")
    
    return tps

if __name__ == "__main__":
    # Baseline run
    inject_tasks(100)
    logs = run_manager_and_audit(20)
    analyze_logs(logs, node_count=3)
