#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--case-type", default="self-heal")
    parser.add_argument("--output", default=".nexus/metrics/learning_gate_calibration.jsonl")
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Starting {args.runs}-run calibration for case type: {args.case_type}")

    for i in range(1, args.runs + 1):
        print(f"\n[Run {i}/{args.runs}] Executing {args.case_type} benchmark...")
        start_time = time.time()
        
        cmd = ["uv", "run", "python", "-m", "pytest", "tests/"] if args.case_type == "regression" else ["uv", "run", "python", "-m", "pytest", "tests/integration/test_incident_replay.py"]
        
        # In a real calibration, we'd trigger the actual workload.
        # We'll just run pytest as a placeholder if case_type isn't specified, 
        # or another script. For simplicity, we'll assume `scripts/replay_case.py` or similar is used.
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            warning_count = result.stderr.count("WARNING")
        except Exception as e:
            print(f"Warning: Failed to execute: {e}")
            warning_count = 0
            
        duration = time.time() - start_time

        print(f"[{i}/{args.runs}] Run completed in {duration:.1f}s. Running acceptance check...")
        
        # Run acceptance check
        subprocess.run(["uv", "run", "scripts/ops/nexus_acceptance_check.py", "--learning-gate-mode", "observe_only"], check=False)
        
        # Load the latest state from jsonl files
        metrics_dir = Path(".nexus/metrics")
        outcome_file = metrics_dir / "skill_outcome_events.jsonl"
        acceptance_file = Path(".nexus/reports/acceptance_report.json")
        
        latest_outcome = {}
        if outcome_file.exists():
            lines = outcome_file.read_text().splitlines()
            if lines:
                latest_outcome = json.loads(lines[-1])
                
        # Actually in Nexus, acceptance check output might be `acceptance_check.json`
        acc_path = Path(".nexus/reports/acceptance_check.json")
        acceptance_pass = False
        learning_gate_pass = False
        if acc_path.exists():
            acc_data = json.loads(acc_path.read_text())
            acceptance_pass = acc_data.get("gate_passed", False)
            learning_gate_pass = acc_data.get("learning_promotion_passed", False)

        def _get_metric(key: str) -> float:
            val = latest_outcome.get(key)
            if val is None:
                val = latest_outcome.get("metadata", {}).get(key, 0.0)
            return float(val) if val is not None else 0.0

        record = {
            "run_id": i,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "pattern_reuse": _get_metric("pattern_reuse"),
            "next_run_hit": _get_metric("next_run_hit"),
            "lesson_quality": _get_metric("lesson_quality"),
            "repair_success": latest_outcome.get("success", False),
            "phantom_blocked": latest_outcome.get("phantom_blocked", False),
            "retry_count": _get_metric("retry_count"),
            "self_heal_retry_count": _get_metric("self_heal_retry_count"),
            "acceptance_pass": acceptance_pass,
            "learning_gate_pass": learning_gate_pass,
            "case_type": args.case_type,
            "duration_secs": round(duration, 2),
            "warning_count": warning_count,
        }

        with output_path.open("a") as f:
            f.write(json.dumps(record) + "\n")
            
        print(f"[{i}/{args.runs}] Record saved. Learning Pass: {learning_gate_pass}, Acceptance Pass: {acceptance_pass}")

    print(f"\nCalibration completed. Data saved to {args.output}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
