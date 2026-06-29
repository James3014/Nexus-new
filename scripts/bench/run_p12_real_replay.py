#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

# Setup repo root path
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.bench.capability_ab_runner import (
    CapabilityTask,
    _finalize_with_nexus_row,
    write_evidence_bundle,
)

def run_p12_replay():
    task_set_path = repo_root / "artifacts" / "runtime" / "full_rerun_task_set.json"
    out_dir = repo_root / "artifacts" / "runtime" / "local_model_armor_p12_real_june_b_replay_v0"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(task_set_path, "r", encoding="utf-8") as f:
        task_set = json.load(f)
        
    tasks = task_set.get("tasks", [])
    
    # Enable Local Model Adapter
    os.environ["NEXUS_WITH_LOCAL_MODEL_ADAPTER"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_DRY_RUN"] = "0"
    os.environ["NEXUS_LOCAL_MODEL_CALL_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE"] = "1"
    os.environ["NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE"] = "1"
    os.environ["NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_GUARD_FAIL_CLOSED_ENABLE"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_PROVIDER"] = "ollama"
    os.environ["NEXUS_LOCAL_MODEL_NAME"] = "qwen2.5-coder:14b-instruct-q3_K_M"
    
    finalized_rows = []
    
    for t in tasks:
        # Construct CapabilityTask
        task = CapabilityTask(
            id=t["instance_id"],
            difficulty="medium",
            task_type="test_repair",
            task_desc=t.get("notes") or "",
            target_file="", # Intentionally empty to test missing controls fallback
            test_file=t.get("verifier_command") or "",
            success_criteria="tests_pass",
        )
        
        row = {
            "mode": "with_nexus",
            "model_calls": 0,
            "total_tokens": 0,
        }
        
        # Execute the pipeline finalization
        finalized = _finalize_with_nexus_row(
            row,
            provider="gemini",
            model_required=True,
            nexus_required=False,
            task=task,
            repo_root=repo_root,
        )
        finalized_rows.append(finalized)
        
    # Write the evidence bundle
    with_path = out_dir / "with_nexus.jsonl"
    without_path = out_dir / "without_nexus.jsonl"
    with_path.write_text("")
    without_path.write_text("")
    
    bundle_path = write_evidence_bundle(
        out_dir=out_dir,
        with_path=with_path,
        without_path=without_path,
        rows=finalized_rows,
        config={
            "tasks_file": "full_rerun_task_set.json",
            "tasks_manifest_hash": "p12_baseline_hash",
            "unique_tasks_requested": len(tasks),
            "repeat_trials": 1,
        }
    )
    
    print(f"P12 Replay Complete. Bundle written to: {bundle_path}")

if __name__ == "__main__":
    run_p12_replay()
