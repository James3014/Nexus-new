#!/usr/bin/env python3
import os
import subprocess
import sys

def main():
    # 1. Ensure we have the latest graph data for ski-test
    repo = "/Users/jameschen/Downloads/skidiy/project/ski-test"
    print("🔄 Updating graph data for ski-test...")
    subprocess.run(["python3", "scripts/engine/collectors/node_collector_v1.py", "--repo", repo, "--out", "skidiy_nodes.jsonl"])
    subprocess.run(["python3", "scripts/engine/collectors/edge_resolver_v1.py", "--repo", repo, "--nodes", "skidiy_nodes.jsonl", "--out", "skidiy_edges.jsonl"])

    # 2. Simulate PR change
    changed_files = "setup_database.sql"
    print(f"🎬 Simulating PR with changed files: {changed_files}")
    
    # 3. Generate Report
    cmd = ["python3", "scripts/engine/ci_graph_impact.py", "--files", changed_files, "--out", "PR_REPORT_DEMO.md"]
    subprocess.run(cmd)

    if os.path.exists("PR_REPORT_DEMO.md"):
        print("\n🏆 PR Impact Report generated successfully: PR_REPORT_DEMO.md")
        # Print a snippet
        with open("PR_REPORT_DEMO.md", "r") as f:
            print("-" * 20)
            print(f.read()[:500] + "...")
            print("-" * 20)
    else:
        print("❌ Failed to generate report.")

if __name__ == "__main__":
    main()
