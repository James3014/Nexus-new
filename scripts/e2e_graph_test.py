#!/usr/bin/env python3
import subprocess
import json
import sys

def run_step(name, cmd):
    print(f"--- Running {name} ---")
    try:
        result = subprocess.check_output(cmd, shell=True).decode()
        print(result)
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ Error in {name}: {e}")
        sys.exit(1)

def main():
    repo = "/Users/jameschen/Downloads/skidiy/project"
    
    # 1. Collect Nodes
    run_step("Node Collection", f"python3 scripts/engine/collectors/node_collector_v1.py --repo {repo} --out test_nodes.jsonl")
    
    # 2. Resolve Edges
    run_step("Edge Resolution", f"python3 scripts/engine/collectors/edge_resolver_v1.py --repo {repo} --nodes test_nodes.jsonl --out test_edges.jsonl")
    
    # 3. Query Impact
    output = run_step("Impact Query", "python3 scripts/engine/nx_impact.py --query questions --nodes test_nodes.jsonl --edges test_edges.jsonl")
    
    # 4. Verify specific files
    expected_files = ["script.js", "quiz_service.py", "build_db.py"]
    all_found = True
    for f in expected_files:
        if f in output:
            print(f"✅ Found expected file in impact set: {f}")
        else:
            print(f"❌ MISSING expected file: {f}")
            all_found = False
    
    if all_found:
        print("\n🏆 E2E Impact Analysis Verification: SUCCESS")
    else:
        print("\n💥 E2E Impact Analysis Verification: FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
