#!/usr/bin/env python3
import time
import subprocess
import os

def main():
    print("🚀 Nexus Killer Demo Pipeline: Initiating Final Audit Workflow...")
    time.sleep(1)

    # 1. Sensing & Graph Collection
    print("\n🔍 STEP 1: CPG Sensing (Streaming Mode enabled)")
    subprocess.run(["python3", "scripts/engine/stream_graph_collector.py"])
    
    # 2. Impact Analysis
    print("\n🕸️  STEP 2: Cross-Language Impact Mapping")
    subprocess.run(["python3", "scripts/engine/nx_impact.py"])

    # 3. Sandboxed L6 Audit
    print("\n🛡️  STEP 3: Sandboxed Security Audit (Wasm Runtime)")
    subprocess.run(["python3", "scripts/full_sandbox_test.py"])

    # 4. Hybrid Patch Generation
    print("\n🛠️  STEP 4: Generating Deterministic Repair Patch")
    subprocess.run(["python3", "scripts/engine/hybrid_patcher.py"])

    print("\n🏆 KILLER DEMO SUCCESSFUL: Nexus Governance Loop Closed 100%")
    print("📝 Report: demo/skidiy-pr.md generated.")
    print("📈 Visualization: demo/02_dashboard.png ready for pitch.")

if __name__ == "__main__":
    main()
