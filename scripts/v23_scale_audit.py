import subprocess
import time
import os
import json
import statistics
import re
from node_fleet_mgr_v22 import start_fleet, stop_fleet
from stress_test_nsp_v22 import inject_tasks, analyze_logs

# ⚡️ Nexus Swarm V23 Queue & Batching Audit
TOKEN = "nexus-secret-2026"
BASE_TPS_3NODES = 0.80 # From Phase 22

def run_manager_and_audit_v23(duration_sec=20):
    print(f"🚀 Launching Refactored Swarm Manager for {duration_sec}s audit...")
    cmd = ["./swarm-manager"]
    env = os.environ.copy()
    env["NEXUS_SWARM_TOKEN"] = TOKEN
    
    proc = subprocess.Popen(cmd, cwd="nexus-swarm", env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Wait for the duration
    time.sleep(duration_sec)
    
    # Send SIGINT to trigger the manager's cleanup and exit
    proc.terminate()
    stdout, stderr = proc.communicate(timeout=5)
    
    return stdout.splitlines()

import socket

def wait_for_ports(ports, timeout=30):
    print(f"⌛ Waiting for {len(ports)} nodes to be ready...")
    start = time.time()
    while time.time() - start < timeout:
        all_ready = True
        for port in ports:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                if s.connect_ex(('localhost', port)) != 0:
                    all_ready = False
                    break
        if all_ready:
            print("✅ All nodes are listening.")
            return True
        time.sleep(1)
    print("⚠️  Warning: Timeout waiting for some nodes.")
    return False

def main():
    print("🚀 Starting Nexus Swarm V23 (Queue v0.2) Audit...")
    
    node_count = 100
    stop_fleet()
    start_fleet(node_count, TOKEN)
    
    # Wait for all ports
    wait_for_ports(range(8001, 8001 + node_count))
    
    inject_tasks(400)
    
    # Run audit
    logs = run_manager_and_audit_v23(20)
    
    tps = analyze_logs(logs, node_count=node_count, baseline_tps=BASE_TPS_3NODES)
    
    if tps == 0:
        print("\n❌ DEBUG: Manager Logs:")
        for l in logs[:50]: # First 50 logs
            print(f"  > {l}")
    
    stop_fleet()

if __name__ == "__main__":
    main()
