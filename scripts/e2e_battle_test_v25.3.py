#!/usr/bin/env python3
import os
import subprocess

def main():
    repo = "/Users/jameschen/Downloads/skidiy/project/ski-test"
    
    # 1. Simulate PR with schema change
    changed_files = "setup_database.sql"
    print(f"🎬 Simulating PR Change to: {changed_files}")
    
    # 2. Generate CI Report
    print("🕸️ Generating CI Impact Report...")
    subprocess.run(["python3", "scripts/engine/ci_graph_impact.py", "--files", changed_files, "--out", "BATTLE_PR_REPORT.md"])
    
    # 3. Detect Fragility & Generate Patch
    # In a real scenario, the CI script would call this. 
    # Here we mock the detection of script.js as a high-risk site.
    print("🛠️ Generating Automated Repair Patch for script.js...")
    subprocess.run(["python3", "scripts/engine/ci_fix_generator.py", "--target", "script.js", "--entity", "questions", "--out", "BATTLE_REPAIR.patch"])

    # 4. Final Summary
    print("\n🏆 Battle Test Results:")
    if os.path.exists("BATTLE_PR_REPORT.md"):
        print("✅ CI Report (Mermaid) produced successfully.")
    if os.path.exists("BATTLE_REPAIR.patch"):
        print("✅ Repair Patch (.patch) produced successfully.")
        with open("BATTLE_REPAIR.patch", "r") as f:
            print("-" * 15 + " PATCH SNIPPET " + "-" * 15)
            print(f.read())
            print("-" * 40)

if __name__ == "__main__":
    main()
