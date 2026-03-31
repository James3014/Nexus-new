#!/usr/bin/env python3
"""
Nexus Soak Test Harness
用來執行長時間穩定度測試 (1h, 6h, 24h)。
重點觀察：Phase Latency 是否慢速膨脹（記憶體/DB session 洩漏）、OOM 機率、以及 Telemetry 斷點。
"""
import argparse
import time
import subprocess
import sys
import psutil
import os
import csv
from pathlib import Path
import json

def get_process_memory() -> float:
    """Return current process memory in MB"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

def run_single_iteration(engine_clicript: Path, root_path: Path) -> dict:
    start_time = time.time()
    # Execute a simple benchmark iteration or a synthetic task
    cmd = [
        "uv", "run", "python",
        str(engine_clicript),
        "nexus:benchmark",
        "--tasks", "2",
        "--output", ".nexus/soak_out.csv"
    ]
    
    res = subprocess.run(
        cmd,
        cwd=str(root_path),
        capture_output=True,
        text=True
    )
    duration = time.time() - start_time
    # Parse phase latency if possible
    # We will log successful completion and time
    
    # Run acceptance check to see Stage 1 signals
    acc_res = subprocess.run(
        ["uv", "run", "python", "scripts/ops/nexus_acceptance_check.py"],
        cwd=str(root_path), capture_output=True, text=True
    )
    
    learning_gate_warn = "LEARNING_GATE_WARN" in acc_res.stdout or "LEARNING_GATE_WARN" in acc_res.stderr
    
    return {
        "success": res.returncode == 0,
        "duration_sec": duration,
        "memory_mb": get_process_memory(),
        "learning_warn": learning_gate_warn
    }

def main():
    parser = argparse.ArgumentParser(description="Nexus Soak Test")
    parser.add_argument("--duration-hours", type=float, default=1.0, help="Duration in hours to run the soak test")
    parser.add_argument("--interval-sec", type=int, default=10, help="Interval between runs")
    args = parser.parse_args()

    root_path = Path(__file__).resolve().parents[2]
    venv_python = root_path / ".venv" / "bin" / "python"
    engine_cli = root_path / "scripts" / "nexus_cli.py"

    if not engine_cli.exists():
        print(f"❌ Cannot find {engine_cli}")
        sys.exit(1)

    duration_sec = args.duration_hours * 3600
    print(f"🌊 [Soak Test] Starting for {args.duration_hours} hours ({duration_sec} sec).")
    
    log_dir = root_path / ".nexus" / "metrics"
    log_dir.mkdir(parents=True, exist_ok=True)
    report_file = log_dir / f"soak_test_report_{int(time.time())}.csv"
    
    start_time = time.time()
    iterations = 0
    failures = 0
    
    with open(report_file, "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["iteration", "timestamp", "success", "duration_sec", "memory_mb"])
        
        while (time.time() - start_time) < duration_sec:
            iterations += 1
            print(f"🔄 Iteration {iterations} (Elapsed: {(time.time() - start_time)/60:.1f}m / {args.duration_hours*60:.1f}m)")
            
            result = run_single_iteration(engine_cli, root_path)
            
            if not result["success"]:
                failures += 1
                print(f"⚠️ Iteration {iterations} failed! Total failures: {failures}")
                
            writer.writerow([
                iterations,
                int(time.time()),
                result["success"],
                f"{result['duration_sec']:.2f}",
                f"{result['memory_mb']:.2f}"
            ])
            f.flush()
            
            time.sleep(args.interval_sec)
            
    print(f"🏁 Soak test complete. Total iterations: {iterations}, Failures: {failures}")
    print(f"📄 Report saved to {report_file}")

if __name__ == "__main__":
    main()
