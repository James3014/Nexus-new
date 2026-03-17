#!/usr/bin/env python3
import subprocess
import sys
import json
from pathlib import Path

def run_step(name, cmd):
    print(f"\n🚀 [CI-Gate] Running: {name}...")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✅ {name} PASSED")
        return True, res.stdout
    else:
        print(f"❌ {name} FAILED")
        print(res.stdout)
        print(res.stderr)
        return False, res.stderr

def main():
    print("🛡️ [Nexus CI Gate] Initializing Automated Audit Lane...")
    
    # 1. Pytest Regression
    success, _ = run_step("Regression Tests", "uv run pytest tests/test_v9_regression_p1.py -q")
    if not success: sys.exit(1)
    
    # 2. Benchmark Replay (Mini-lane)
    benchmark_cmd = "uv run scripts/nexus_cli.py nexus:benchmark --tasks 10 --output ci_benchmark.csv"
    success, _ = run_step("Benchmark Replay", benchmark_cmd)
    if not success: sys.exit(1)
    
    # 3. Drift & Health Check
    try:
        import csv
        with open("ci_benchmark.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        healths = [float(r["health"]) for r in rows if r["health"]]
        drifts = [float(r["drift"]) for r in rows if r["drift"]]
        
        avg_health = sum(healths) / len(healths) if healths else 0
        max_drift = max(drifts) if drifts else 0
        
        print(f"\n📊 [CI-Gate Metrics]")
        print(f"- Average Health: {avg_health:.1f}%")
        print(f"- Max Drift: {max_drift:.2f}")
        
        if avg_health < 90:
            print(f"❌ Failure: Average health {avg_health:.1f}% dropped below 90%!")
            sys.exit(1)
        if max_drift > 0.5:
            print(f"❌ Failure: Max drift {max_drift:.2f} exceeded 0.5 threshold!")
            sys.exit(1)
            
        print("\n🎉 [CI-Gate] ALL QUALITY GATES PASSED!")
    except Exception as e:
        print(f"❌ Error during metrics validation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
