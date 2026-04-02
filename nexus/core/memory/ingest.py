from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import os
from datetime import datetime
from .schema import EpisodicMemory

def ingest_task_result(run_id: str, task_result_path: str, output_path: str = "episodic_memory.jsonl"):
    """
    Ingest a task result from a JSON file into an episodic memory JSONL file.
    """
    path = Path(task_result_path)
    if not path.exists():
        print(f"Error: Task result file {task_result_path} not found.")
        return

    with open(path, "r") as f:
        data = json.load(f)

    # Assuming task_result.json contains fields that can be mapped to EpisodicMemory.
    # We might need to handle cases where some fields are missing.
    
    # Example mapping (adjust based on actual task_result.json structure if known)
    memory_data = {
        "run_id": run_id,
        "task_id": data.get("task_id", "unknown-task"),
        "state_before": data.get("state_before", {}),
        "action": data.get("action", {}),
        "state_after": data.get("state_after", {}),
        "reward": data.get("reward", 0.0),
        "timestamp": data.get("timestamp", datetime.now().isoformat())
    }

    # Validate with schema
    memory = EpisodicMemory(**memory_data)

    # Write to JSONL
    with open(output_path, "a") as f:
        f.write(memory.model_dump_json() + "\n")
    
    print(f"Successfully ingested task result from {task_result_path} to {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingest task result into episodic memory.")
    parser.add_argument("--run-id", required=True, help="The run ID of the task.")
    parser.add_argument("--input", required=True, help="Path to the task_result.json file.")
    parser.add_argument("--output", default="episodic_memory.jsonl", help="Path to the episodic_memory.jsonl file.")
    
    args = parser.parse_args()
    ingest_task_result(args.run_id, args.input, args.output)
