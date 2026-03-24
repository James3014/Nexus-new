#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from pathlib import Path
from datasets import load_dataset

def main():
    parser = argparse.ArgumentParser(description="Official SWE-bench Lite Harness for Nexus")
    parser.add_argument("--mode", default="verified", help="Benchmark mode")
    parser.add_argument("--limit", type=int, default=100, help="Number of tasks")
    parser.add_argument("--model", required=True, help="Model ID")
    parser.add_argument("--jsonl-output", default="results.jsonl", help="Output JSONL")
    
    args = parser.parse_args()
    
    print(f"🚀 [SWE-bench] Starting {args.mode} evaluation (Limit: {args.limit})")
    
    # 1. Load Dataset
    print("📥 Loading Dataset...")
    dataset = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    if args.limit:
        dataset = dataset.select(range(args.limit))
    
    # 2. Inference Loop
    predictions = []
    preds_file = Path("predictions.jsonl")
    with open(preds_file, "w") as f:
        for item in dataset:
            instance_id = item["instance_id"]
            print(f"🔍 [Inference] Processing {instance_id}...")
            
            # Call Nexus v16
            cmd = [
                "/Users/jameschen/.local/bin/uv", "run", "scripts/engine/nexus_cli.py",
                "nexus:runner", "--task", item["problem_statement"],
                "--audit-level", "bypass"
            ]
            # Enable Benchmark Mode in Env
            env = os.environ.copy()
            env["NEXUS_BENCHMARK_MODE"] = "1"
            
            subprocess.run(cmd, capture_output=True, text=True, cwd="/Users/jameschen/Workspace/nexus", env=env)
            
            # Extract Patch
            runs_dir = Path("/Users/jameschen/Workspace/nexus/.nexus/runs")
            # Filter for task dirs only
            task_dirs = sorted([d for d in runs_dir.glob("task-*") if d.is_dir()], key=os.path.getmtime)
            latest_run = task_dirs[-1]
            
            # Attempt to find patch
            patch = ""
            patch_file = latest_run / "patch.diff"
            if patch_file.exists():
                patch = patch_file.read_text()
            else:
                # Fallback to general .patch
                patches = list(latest_run.glob("*.patch"))
                if patches:
                    patch = patches[0].read_text()
            
            pred = {
                "instance_id": instance_id,
                "model_patch": patch,
                "model_name_or_path": args.model
            }
            f.write(json.dumps(pred) + "\n")
            
    # 3. Evaluation (Official Harness)
    print("🧪 [Evaluation] Running Official Pytest Suite...")
    eval_cmd = [
        "/Users/jameschen/.local/bin/uv", "run", "--with", "swebench",
        "python3", "-m", "swebench.harness.run_evaluation",
        "--dataset_name", "princeton-nlp/SWE-bench_Verified",
        "--predictions_path", str(preds_file),
        "--max_workers", "8",
        "--run_id", f"nexus-eval-{int(time.time())}"
    ]
    subprocess.run(eval_cmd, cwd="/Users/jameschen/Workspace/nexus")
    
    print("✅ [SWE-bench] Full Cycle Complete.")

if __name__ == "__main__":
    import time
    main()
