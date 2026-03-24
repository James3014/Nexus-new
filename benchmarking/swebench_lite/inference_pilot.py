import json
import os
import subprocess
from datasets import load_dataset
from pathlib import Path

# Config
DATASET_NAME = "princeton-nlp/SWE-bench_Verified"
MODEL_NAME = "nexus-v16"
LIMIT = 5
OUTPUT_FILE = "/Users/jameschen/Workspace/nexus/benchmarking/swebench_lite/predictions_pilot.jsonl"
NEXUS_CLI = "/Users/jameschen/.local/bin/uv run scripts/engine/nexus_cli.py"

def run_nexus_inference(instance_id, problem_statement):
    # Call Nexus CLI to get a patch
    # We use a simplified call for now
    cmd = [
        "/Users/jameschen/.local/bin/uv", "run", "scripts/engine/nexus_cli.py",
        "nexus:runner",
        "--task", problem_statement,
        "--limit", "1",
        "--mode", "engineering"
    ]
    try:
        # In a real scenario, we would parse the actual diff from Nexus output
        # For this pilot, we'll simulate or capture the output
        # NOTE: Nexus usually writes results to .nexus/runs/
        result = subprocess.run(cmd, capture_output=True, text=True, cwd="/Users/jameschen/Workspace/nexus")
        # Find the latest task directory
        latest_task = sorted(Path("/Users/jameschen/Workspace/nexus/.nexus/runs").glob("task-*"), key=os.path.getmtime)[-1]
        # We assume Nexus generated a diff or similar. 
        # In this POC, we'll try to find any .patch file or use the .musestate logs
        # Actually, let's assume Nexus produces a 'patch.diff' or similar if integrated
        return "simulate_patch_for_" + instance_id # Placeholder for now
    except Exception as e:
        print(f"Error running Nexus for {instance_id}: {e}")
        return ""

def main():
    print(f"Loading {DATASET_NAME}...")
    dataset = load_dataset(DATASET_NAME, split="test")
    subset = dataset.select(range(LIMIT))
    
    with open(OUTPUT_FILE, "w") as f:
        for item in subset:
            instance_id = item["instance_id"]
            print(f"Processing {instance_id}...")
            patch = run_nexus_inference(instance_id, item["problem_statement"])
            
            result = {
                "instance_id": instance_id,
                "model_patch": patch,
                "model_name_or_path": MODEL_NAME
            }
            f.write(json.dumps(result) + "\n")
            print(f"Finished {instance_id}")

if __name__ == "__main__":
    main()
