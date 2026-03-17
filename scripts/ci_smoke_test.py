#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

def run_smoke():
    project_root = Path(__file__).resolve().parents[1]
    print("🚀 [CI:Smoke] Starting Nexus Automated Replay Runner...")
    
    # 1. Run Replay for OFF-001 with bypass audit
    cmd = [
        "/Users/jameschen/.local/bin/uv", "run", 
        "scripts/replay_case.py", "OFF-001"
    ]
    
    print(f"  - Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(project_root))
    
    if result.returncode == 0:
        print("✅ [CI:Smoke] OFF-001 Passed.")
    else:
        print("❌ [CI:Smoke] OFF-001 Failed.")
        sys.exit(1)

    print("🎉 [CI:Smoke] All automation lanes passed.")

if __name__ == "__main__":
    run_smoke()
