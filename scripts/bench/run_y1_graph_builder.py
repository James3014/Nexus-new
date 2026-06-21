#!/usr/bin/env python3
"""Y1 — Evidence Graph Builder script."""
import json
import os
from pathlib import Path
from nexus.services.local_heal.evidence_graph import EvidenceGraphBuilder

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
ACCEPTED_TASKS_FILE = REPO_ROOT / "artifacts" / "runtime" / "x1_hard_real_repair_task_expansion_v0" / "accepted_task_set.json"
OUTPUT_DIR = REPO_ROOT / "artifacts" / "runtime" / "y1_evidence_graph_v0"
EXAMPLES_DIR = OUTPUT_DIR / "graph_examples"


def main():
    print("Running Y1 Evidence Graph Builder...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load accepted tasks
    if not ACCEPTED_TASKS_FILE.exists():
        print(f"Error: {ACCEPTED_TASKS_FILE} not found!")
        # Fallback list if file is missing
        tasks = [
            {"task_id": "sympy__sympy-14096", "repo": "sympy"},
            {"task_id": "django__django-11505", "repo": "django"},
            {"task_id": "django__django-13455", "repo": "django"},
        ]
    else:
        with open(ACCEPTED_TASKS_FILE, "r") as f:
            tasks = json.load(f)

    builder = EvidenceGraphBuilder()
    results = {}
    missing_report = {}

    # 2. Build graph for each task
    for task in tasks:
        task_id = task["task_id"]
        repo = task["repo"]
        print(f"Building graph for task: {task_id}")
        
        graph = builder.build(task_id, repo)
        g_dict = graph.to_dict()
        results[task_id] = g_dict

        # Collect missing context risks
        if graph.missing_context_risks:
            missing_report[task_id] = {
                "missing_context_risks": graph.missing_context_risks,
                "confidence_score": graph.evidence_confidence
            }

        # Write examples for hard tasks
        if "sympy-14096" in task_id:
            with open(EXAMPLES_DIR / "sympy_14096_graph.json", "w") as f:
                json.dump(g_dict, f, indent=2)
        elif "django-11505" in task_id:
            with open(EXAMPLES_DIR / "django_11505_graph.json", "w") as f:
                json.dump(g_dict, f, indent=2)

    # 3. Save graph builder results
    with open(OUTPUT_DIR / "graph_builder_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # 4. Save missing context report
    with open(OUTPUT_DIR / "missing_context_report.json", "w") as f:
        json.dump(missing_report, f, indent=2)

    print("Y1 Evidence Graph Builder completed successfully.")


if __name__ == "__main__":
    main()
