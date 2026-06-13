#!/usr/bin/env python3
"""
scripts/bench/s2t_memory_sidecar_shadow.py

Runner for the 3B Memory Sidecar in shadow mode.
Takes task artifacts and produces a schema-valid checkpoint.
"""
import argparse
import json
import sys
import hashlib
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

def load_json_file(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def read_text_file(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser(description="Nexus S2T Memory Sidecar Shadow Runner")
    parser.add_argument("--task-id", required=True, help="Task Identifier")
    parser.add_argument("--receipt", help="Path to task receipt JSON")
    parser.add_argument("--log", help="Path to execution log")
    parser.add_argument("--git-diff-stat", help="Path to git diff stat")
    parser.add_argument("--test-output", help="Path to test output log")
    parser.add_argument("--plan", help="Path to implementation plan")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--mock", action="store_true", help="Run with mock logic (for testing)")

    args = parser.parse_args()

    # Load Inputs
    receipt_data = load_json_file(args.receipt)
    log_content = read_text_file(args.log)
    diff_stat = read_text_file(args.git_diff_stat)
    test_output = read_text_file(args.test_output)
    plan_content = read_text_file(args.plan)

    # In a real run, this is where the 3B model would be invoked.
    # For this prototype phase, we simulate or use mock logic.
    
    checkpoint: Dict[str, Any] = {
        "schema": "nexus.s2t_memory_sidecar_checkpoint.v1",
        "task_id": args.task_id,
        "mode": "unknown",
        "summary": "Shadow sidecar initialized.",
        "completed_steps": [],
        "open_blockers": [],
        "failure_family": None,
        "evidence_refs": [],
        "modified_files": [],
        "test_commands": [],
        "test_results": [],
        "next_action": "wait_for_instruction",
        "claim_boundary": "unknown",
        "do_not_repeat": [],
        "confidence": "low",
        "abstain_reason": None
    }

    if args.mock:
        # Simple mock logic based on inputs
        checkpoint["summary"] = f"Mock summary for {args.task_id}"
        checkpoint["mode"] = "bootstrapping"
        if receipt_data:
            checkpoint["evidence_refs"].append(args.receipt)
            checkpoint["confidence"] = "medium"
        if not log_content and not receipt_data:
            checkpoint["abstain_reason"] = "insufficient_input_evidence"
            checkpoint["claim_boundary"] = "unknown"
        else:
            checkpoint["claim_boundary"] = "observation_only"

    # Validation (Basic)
    if not args.mock and not receipt_data and not log_content:
         checkpoint["abstain_reason"] = "no_input_provided"
         checkpoint["summary"] = "Abstained due to missing inputs."

    # Write Output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    row = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "task_id": args.task_id,
        "checkpoint": checkpoint,
        "input_hashes": {
            "receipt": hashlib.sha256(json.dumps(receipt_data).encode()).hexdigest() if receipt_data else None,
            "log": hashlib.sha256(log_content.encode()).hexdigest() if log_content else None
        }
    }

    with output_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

    print(f"Checkpoint written to {args.output}")

if __name__ == "__main__":
    main()
