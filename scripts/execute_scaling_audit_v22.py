import subprocess
import time
import os
import json
import statistics
import re
from node_fleet_mgr_v22 import start_fleet, stop_fleet
from stress_test_nsp_v22 import inject_tasks, run_manager_and_audit, analyze_logs

# 🌀 Nexus Swarm Commercial Scaling Audit Master
TOKEN = "nexus-secret-2026"

def run_tier(node_count, baseline_tps=None):
    print(f"\n🌀 === TIER: {node_count} NODES ===")
    stop_fleet()
    start_fleet(node_count, TOKEN)
    time.sleep(5) # Warm up
    
    inject_tasks(min(node_count * 5, 200)) # Scale tasks with nodes
    logs = run_manager_and_audit(20)
    
    tps = analyze_logs(logs, node_count=node_count, baseline_tps=baseline_tps)
    stop_fleet()
    return tps

def main():
    print("🚀 Starting Nexus Swarm Scaling Audit (v22.1)...")
    
    # 1. Baseline (3 Nodes)
    baseline_tps = run_tier(3)
    
    # 2. Scale-Out (30 Nodes)
    tps_30 = run_tier(30, baseline_tps=baseline_tps)
    
    # 3. Stress-Limit (100 Nodes)
    tps_100 = run_tier(100, baseline_tps=baseline_tps)
    
    print("\n🏆 Scaling Audit Completed.")
    print(f"📊 Summary:")
    print(f"  - 3 Nodes:  {baseline_tps:.2f} TPS")
    print(f"  - 30 Nodes: {tps_30:.2f} TPS")
    print(f"  - 100 Nodes: {tps_100:.2f} TPS")

if __name__ == "__main__":
    main()
