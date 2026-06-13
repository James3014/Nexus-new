
import json
import argparse
import sys
import hashlib
import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path for local imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.s2t_memory_sidecar_shadow import MemorySidecarAdvisor

def evaluate_shadow(mock_mode: bool = False):
    base_reports_dir = Path(".nexus/reports/local_heal")
    output_file = Path(".nexus/metrics/s2t_memory_sidecar_shadow_eval.jsonl")
    
    # 1. Identify valid task directories
    task_dirs = []
    if base_reports_dir.exists():
        for d in base_reports_dir.iterdir():
            if d.is_dir() and (d / "receipt.json").exists():
                task_dirs.append(d)
    
    print(f"Found {len(task_dirs)} potential task reports.")
    
    # 2. Pilot evaluation (30 rows)
    pilot_tasks = task_dirs[:30]
    
    # 3. Initialize Advisor
    advisor = MemorySidecarAdvisor(
        adapter_path="training/adapters/qwen3b_s2t_adapter_v2",
        force_simulation=mock_mode
    )
    
    print(f"Starting Shadow Evaluation (Mock={mock_mode})...")
    
    # Clear output file first
    if output_file.exists(): output_file.unlink()
    
    results = []
    for t_dir in pilot_tasks:
        task_id = t_dir.name
        print(f"Processing task: {task_id}")
        
        # Load Artifacts
        receipt_path = t_dir / "receipt.json"
        log_path = t_dir / "repro_evidence.log"
        if not log_path.exists():
            log_path = t_dir / "execution.log" # Fallback
            
        diff_path = t_dir / "patch.diff"
        test_path = t_dir / "verification_report.txt"
        
        def read_file(p):
            return p.read_text(encoding="utf-8") if p.exists() else ""

        artifacts = {
            "receipt": read_file(receipt_path),
            "log": read_file(log_path),
            "diff_stat": read_file(diff_path),
            "test_output": read_file(test_path),
            "plan": ""
        }
        
        checkpoint = advisor.generate_checkpoint(task_id, artifacts)
        
        row = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "task_id": task_id,
            "checkpoint": checkpoint,
            "metrics": {
                "schema_compliance": checkpoint.get("schema") == "nexus.s2t_memory_sidecar_checkpoint.v1",
                "abstained": checkpoint.get("abstain_reason") is not None
            }
        }
        results.append(row)
        
        # Write incrementally
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
            
    print(f"Evaluation complete. Results in {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    evaluate_shadow(mock_mode=args.mock)
