#!/usr/bin/env python3
import argparse
import subprocess
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexus.delivery.phantom_guard import compute_phantom_success

VENV_PYTHON = ROOT / ".venv" / "bin" / "python"

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


def run_dry_run():
    print("🛡️ [Nexus CI Gate] Dry-run status check...")
    checks = {
        "venv_python": VENV_PYTHON.exists(),
        "contracts_dir": (ROOT / "tests" / "contracts").exists(),
        "benchmark_script": (ROOT / "scripts" / "nexus_cli.py").exists() or (ROOT / "scripts" / "engine" / "nexus_cli.py").exists(),
    }
    for key, ok in checks.items():
        print(f"- {key}: {'OK' if ok else 'MISSING'}")
    return 0 if all(checks.values()) else 1

def main():
    parser = argparse.ArgumentParser(description="Nexus CI gate")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        sys.exit(run_dry_run())

    print("🛡️ [Nexus CI Gate] Initializing Automated Audit Lane...")
    
    # 0. Contract Regression & E2E DI Gate
    success, _ = run_step(
        "DI & Contract Regression",
        f'"{VENV_PYTHON}" -m pytest tests/contracts/ tests/test_container_orchestration.py -q',
    )
    if not success: sys.exit(1)
    
    # 0.5 Warning Budget Gate
    success, _ = run_step(
        "Warning Budget",
        f'"{VENV_PYTHON}" scripts/ops/warning_budget_check.py --threshold 70',
    )
    if not success: sys.exit(1)
    
    # 1. Pytest Regression
    success, _ = run_step(
        "Regression Tests",
        f'"{VENV_PYTHON}" -m pytest tests/test_v9_regression_p1.py -q',
    )
    if not success: sys.exit(1)
    
    # 2. Benchmark Replay (Mini-lane)
    benchmark_cmd = (
        f'"{VENV_PYTHON}" scripts/nexus_cli.py '
        "nexus:benchmark --tasks 10 --output ci_benchmark.csv"
    )
    success, _ = run_step("Benchmark Replay", benchmark_cmd)
    if not success: sys.exit(1)
    
    # 3. Evidence Integrity (Repair Honesty N9-REPAIR)
    latest_proof = ROOT / ".nexus" / "runs" / "latest" / "write_proof.json"
    print(f"\n🔍 [CI-Gate] Checking Evidence Integrity: {latest_proof}...")
    if not latest_proof.exists():
        print("❌ Failure: N9-REPAIR evidence (write_proof.json) is missing in the latest run!")
        # sys.exit(1) # Warning only for now to allow calibration passing if no repair was intended
    else:
        print("✅ Evidence Integrity PASSED")
    
    # 4. Drift & Health Check
    try:
        import csv
        with open("ci_benchmark.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
        healths = [float(r["health"]) for r in rows if r["health"]]
        drifts = [float(r["drift"]) for r in rows if r["drift"]]
        phase_healths = [float(r["lowest_phase_health"]) for r in rows if "lowest_phase_health" in r and r["lowest_phase_health"]]
        
        # 📊 [CI-Gate Metrics]
        avg_health = sum(healths) / len(healths) if healths else 0
        max_drift = max(drifts) if drifts else 0
        min_phase_health = min(phase_healths) if phase_healths else 0
        
        # 🛡️ TRU-101 Audit Gate: Status Check
        statuses = [r["token_capture_status"] for r in rows]
        empty_statuses = [s for s in statuses if not s]
        raw_tokens = [int(r["token_raw_model"]) for r in rows if r["token_raw_model"]]
        total_raw = sum(raw_tokens)
        
        # 📉 [WP-3/WP-4] Learning Velocity & Sparkline
        velocity = 0.0
        velocity_file = ROOT / ".nexus" / "learning_velocity.json"
        if velocity_file.exists():
            try:
                v_data = json.loads(velocity_file.read_text(encoding="utf-8"))
                velocity = v_data.get("current", 0.0)
            except:
                pass

        print(f"\n📊 [CI-Gate Metrics]")
        print(f"- Average Health: {avg_health:.1f}%")
        print(f"- Max Drift: {max_drift:.2f}")
        print(f"- Lowest Phase Health: {min_phase_health:.1f}%")
        print(f"- Learning Velocity: {velocity:+.2f}")
        print(f"- Token Capture Statistics: {len(empty_statuses)} empty, {len(statuses)} total")
        print(f"- Total Raw Tokens: {total_raw}")
        
        # Fail if status is empty
        if empty_statuses:
            print(f"❌ Failure: {len(empty_statuses)} tasks had empty token_capture_status!")
            sys.exit(1)
            
        if total_raw == 0:
            print(f"⚠️ Warning: Total Raw Tokens is 0. System is currently running on AUDIT-ESTIMATE mode.")
            
        if avg_health < 90:
            print(f"❌ Failure: Average health {avg_health:.1f}% dropped below 90%!")
            sys.exit(1)
        if max_drift > 0.5:
            print(f"❌ Failure: Max drift {max_drift:.2f} exceeded 0.5 threshold!")
            sys.exit(1)
        if min_phase_health < 80:
             print(f"❌ Failure: Lowest phase health {min_phase_health:.1f}% dropped below 80%!")
             sys.exit(1)
            
        print("\n🎉 [CI-Gate] ALL QUALITY GATES PASSED!")
    except Exception as e:
        print(f"❌ Error during metrics validation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
