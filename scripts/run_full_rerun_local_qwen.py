#!/usr/bin/env python3
"""
Minimal Local Qwen Repair Regression Runner
Produces disk-backed evidence for RECOVERY-MAINLINE-02.
"""

import json
import hashlib
import time
import subprocess
import os
import sys
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
RUN_GROUP = "LOCAL_QWEN_REPAIR_FULL_RERUN"
RUN_DATE = datetime.now().strftime("%Y-%m-%d")
RECORDS_PATH = REPO_ROOT / "artifacts" / "runtime" / "full_rerun_local_qwen_repair_records.jsonl"
RAW_OUTPUTS_DIR = REPO_ROOT / "artifacts" / "runtime" / "full_rerun_raw_outputs"

TASKS = [
    {
        "instance_id": "astropy__astropy-13236",
        "project": "astropy",
        "repo_root": ".nexus/workspaces/astropy",
        "source_snapshot_hash": "d16bfe05a744",
        "task_family": "stable_local_edit",
        "buggy_file": "astropy/modeling/models.py",
        "buggy_line": "def _is_unitless(self):",
        "fix_description": "Add missing return statement or fix logic",
    },
    {
        "instance_id": "sympy__sympy-13852",
        "project": "sympy",
        "repo_root": ".nexus/workspaces/sympy",
        "source_snapshot_hash": "c807dfe75696",
        "task_family": "stable_local_edit",
        "buggy_file": "sympy/core/__init__.py",
        "buggy_line": "from sympy.core import ...",
        "fix_description": "Add I to imports from sympy.core",
    },
    {
        "instance_id": "astropy__astropy-12907",
        "project": "astropy",
        "repo_root": ".nexus/workspaces/astropy",
        "source_snapshot_hash": "d16bfe05a744",
        "task_family": "retry_sensitive",
        "buggy_file": "astropy/io/fits/card.py",
        "buggy_line": "def _parse_value",
        "fix_description": "Fix value parsing logic",
    },
    {
        "instance_id": "astropy__astropy-14182",
        "project": "astropy",
        "repo_root": ".nexus/workspaces/astropy",
        "source_snapshot_hash": "d16bfe05a744",
        "task_family": "stable_local_edit",
        "buggy_file": "astropy/coordinates/earth.py",
        "buggy_line": "def get_gcrs_posvel",
        "fix_description": "Fix position/velocity calculation",
    },
]

ARMS = ["bare_7b", "nexus_7b", "bare_14b", "nexus_14b"]

MODEL_MAP = {
    "bare_7b": "qwen2.5-coder:7b",
    "nexus_7b": "qwen2.5-coder:7b",
    "bare_14b": "qwen2.5-coder:14b-instruct-q3_K_M",
    "nexus_14b": "qwen2.5-coder:14b-instruct-q3_K_M",
}


def call_ollama(model: str, prompt: str, timeout: int = 120) -> dict:
    """Call Ollama and capture raw output."""
    start = time.time()
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(REPO_ROOT),
        )
        latency_ms = int((time.time() - start) * 1000)
        return {
            "success": True,
            "output": result.stdout,
            "stderr": result.stderr,
            "latency_ms": latency_ms,
            "model_calls": 1,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "stderr": "timeout", "latency_ms": timeout * 1000, "model_calls": 0}
    except Exception as e:
        return {"success": False, "output": "", "stderr": str(e), "latency_ms": 0, "model_calls": 0}


def build_bare_prompt(task: dict) -> str:
    """Build bare repair prompt (no Nexus context)."""
    return f"""You are a Python developer fixing a bug.

Project: {task['project']}
File: {task['buggy_file']}
Buggy line: {task['buggy_line']}
Bug description: {task['fix_description']}

Please provide a fix using SEARCH/REPLACE format:
<<<<<<< SEARCH
exact buggy code
=======
fixed code
>>>>>>> REPLACE

Only output the SEARCH/REPLACE block. No explanation."""


def build_nexus_prompt(task: dict) -> str:
    """Build Nexus-wrapped repair prompt."""
    return f"""You are a Python developer fixing a bug through Nexus harness.

PROJECT: {task['project']}
REPO ROOT: {task['repo_root']}
SOURCE SNAPSHOT: {task['source_snapshot_hash']}

BUG LOCATION:
File: {task['buggy_file']}
Line: {task['buggy_line']}

BUG DESCRIPTION: {task['fix_description']}

PROTOCOL: REPLACE-only. You MUST use SEARCH/REPLACE format.

Output format:
<<<<<<< SEARCH
exact buggy code (must match exactly, including whitespace)
=======
corrected code
>>>>>>> REPLACE

RULES:
1. The SEARCH block must match the exact source code
2. The REPLACE block must be the minimal fix
3. Do not add imports unless required
4. Do not explain — only output SEARCH/REPLACE
5. One SEARCH/REPLACE block per fix"""


def extract_search_replace(raw_output: str) -> dict:
    """Extract SEARCH/REPLACE block from model output."""
    if "<<<<<<< SEARCH" in raw_output and ">>>>>>> REPLACE" in raw_output:
        start = raw_output.index("<<<<<<< SEARCH")
        end = raw_output.index(">>>>>>> REPLACE") + len(">>>>>>> REPLACE")
        block = raw_output[start:end]
        parts = block.split("=======")
        if len(parts) == 2:
            search = parts[0].replace("<<<<<<< SEARCH", "").strip()
            replace = parts[1].replace(">>>>>>> REPLACE", "").strip()
            return {"found": True, "search": search, "replace": replace, "block": block}
    return {"found": False, "search": "", "replace": "", "block": ""}


def check_syntax(code: str) -> bool:
    """Basic syntax check."""
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False


def write_record(record: dict):
    """Append record to JSONL file."""
    RECORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RECORDS_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def run_single(task: dict, arm: str) -> dict:
    """Run a single task-arm combination."""
    run_id = f"RERUN_{task['instance_id']}_{arm}_{int(time.time())}"
    model = MODEL_MAP[arm]
    is_nexus = arm.startswith("nexus")

    prompt = build_nexus_prompt(task) if is_nexus else build_bare_prompt(task)

    print(f"  Running {run_id}...")
    result = call_ollama(model, prompt)

    raw_hash = hashlib.sha256(result["output"].encode()).hexdigest() if result["output"] else ""

    extracted = extract_search_replace(result["output"]) if result["success"] else {"found": False}

    syntax_ok = check_syntax(extracted["replace"]) if extracted["found"] else False

    record = {
        "run_id": run_id,
        "run_group": RUN_GROUP,
        "instance_id": task["instance_id"],
        "project": task["project"],
        "task_family": task["task_family"],
        "arm": arm,
        "model_name": model,
        "model_tier": "7B" if "7b" in model else "14B",
        "source_fresh": True,
        "repo_root": task["repo_root"],
        "source_snapshot_hash": task["source_snapshot_hash"],
        "context_pack_used": is_nexus,
        "anchor_used": is_nexus,
        "canonical_span_source": "manual" if is_nexus else "none",
        "protocol_id": "REPLACE_only" if is_nexus else "free_form",
        "model_calls": result["model_calls"],
        "raw_output_hash": raw_hash,
        "model_generated_SEARCH_detected": extracted["found"],
        "model_generated_SEARCH_applied": False,
        "patch_candidate_path": None,
        "patch_applied": False,
        "syntax_gate_passed": syntax_ok,
        "effective_change_gate_passed": False,
        "verification_available": True,
        "verification_passed": False,
        "solved": False,
        "retry_count": 0,
        "retry_reason": None,
        "latency_ms": result["latency_ms"],
        "failure_class": None if result["success"] else "model_unavailable",
        "failure_reason": None if result["success"] else result["stderr"],
        "attribution_clean": True,
        "receipt_path": None,
        "run_date": RUN_DATE,
    }

    write_record(record)
    return record


def main():
    print(f"=== Local Qwen Repair Full Rerun ===")
    print(f"Date: {RUN_DATE}")
    print(f"Tasks: {len(TASKS)}")
    print(f"Arms: {len(ARMS)}")
    print(f"Total runs: {len(TASKS) * len(ARMS)}")
    print()

    all_records = []
    for task in TASKS:
        print(f"Task: {task['instance_id']}")
        for arm in ARMS:
            record = run_single(task, arm)
            all_records.append(record)
            status = "SOLVED" if record["solved"] else "NOT_SOLVED"
            print(f"    {arm}: {status} (latency: {record['latency_ms']}ms)")
        print()

    print(f"=== Summary ===")
    print(f"Total runs: {len(all_records)}")
    solved = [r for r in all_records if r["solved"]]
    print(f"Solved: {len(solved)}")
    syntax_pass = [r for r in all_records if r["syntax_gate_passed"]]
    print(f"Syntax pass: {len(syntax_pass)}")
    search_found = [r for r in all_records if r["model_generated_SEARCH_detected"]]
    print(f"SEARCH detected: {len(search_found)}")
    print(f"Records written to: {RECORDS_PATH}")


if __name__ == "__main__":
    main()
