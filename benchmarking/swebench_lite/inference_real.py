import json
import os
import subprocess
from datasets import load_dataset
from pathlib import Path

# Config
DATASET_NAME = "princeton-nlp/SWE-bench_Verified"
MODEL_NAME = "nexus-v16"
LIMIT = 1  # Start with 1 to verify the full chain
OUTPUT_FILE = "/Users/jameschen/Workspace/nexus/benchmarking/swebench_lite/predictions_real_1.jsonl"

def run_nexus_inference(instance_id, problem_statement):
    print(f"Launching Nexus for {instance_id}...")
    # Call Nexus CLI
    cmd = [
        "/Users/jameschen/.local/bin/uv", "run", "scripts/engine/nexus_cli.py",
        "nexus:runner",
        "--task", problem_statement,
        "--limit", "1",
        "--mode", "engineering"
    ]
    try:
        # Run Nexus
        subprocess.run(cmd, capture_output=True, text=True, cwd="/Users/jameschen/Workspace/nexus")
        
        # Find the latest task directory
        runs_dir = Path("/Users/jameschen/Workspace/nexus/.nexus/runs")
        task_dirs = sorted(runs_dir.glob("task-*"), key=os.path.getmtime)
        if not task_dirs:
            return ""
        
        latest_task = task_dirs[-1]
        print(f"Nexus finished. Checking {latest_task}...")
        
        # In Nexus v16, we look for 'patch.diff' or similar
        # Typically, Nexus might store the diff in .musestate or as a separate file
        # Let's check for any .diff or .patch files first
        patches = list(latest_task.glob("*.patch")) + list(latest_task.glob("*.diff"))
        if patches:
            return patches[0].read_text()
            
        # Fallback: Check .musestate for the result
        state_file = latest_task / ".musestate"
        if state_file.exists():
            data = json.loads(state_file.read_text().splitlines()[-1])
            # Assuming Nexus records the patch somewhere in metadata
            return data.get("metadata", {}).get("patch", "")
            
        return ""
    except Exception as e:
        print(f"Error running Nexus for {instance_id}: {e}")
        return ""

def main():
    print(f"Loading {DATASET_NAME}...")
    dataset = load_dataset(DATASET_NAME, split="test")
    # Take the first item for testing
    item = dataset[0]
    instance_id = item["instance_id"]
    
    print(f"Processing {instance_id}...")
    patch = run_nexus_inference(instance_id, item["problem_statement"])
    
    result = {
        "instance_id": instance_id,
        "model_patch": patch,
        "model_name_or_path": MODEL_NAME
    }
    
    with open(OUTPUT_FILE, "w") as f:
        f.write(json.dumps(result) + "\n")
    print(f"Finished {instance_id}. Patch Length: {len(patch)}")

if __name__ == "__main__":
    main()
