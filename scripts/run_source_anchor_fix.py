#!/usr/bin/env python3
"""
Source Anchoring Fix + Tiny Rerun
Nexus owns source anchor, Qwen outputs replacement body only.
"""

import json
import hashlib
import time
import subprocess
import os
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
RUN_GROUP = "SOURCE_ANCHOR_FIX_RERUN"
RUN_DATE = datetime.now().strftime("%Y-%m-%d")
RECORDS_PATH = REPO_ROOT / "artifacts" / "runtime" / "source_anchor_fix_records.jsonl"

TASKS = [
    {
        "instance_id": "astropy__astropy-13236",
        "project": "astropy",
        "workspace": ".nexus/workspaces/astropy",
        "file": "astropy/modeling/models.py",
        "target_function": "_is_unitless",
        "task_family": "stable_local_edit",
    },
    {
        "instance_id": "sympy__sympy-13852",
        "project": "sympy",
        "workspace": ".nexus/workspaces/sympy",
        "file": "sympy/core/__init__.py",
        "target_function": None,
        "task_family": "stable_local_edit",
    },
    {
        "instance_id": "astropy__astropy-12907",
        "project": "astropy",
        "workspace": ".nexus/workspaces/astropy",
        "file": "astropy/io/fits/card.py",
        "target_function": "_parse_value",
        "task_family": "retry_sensitive",
    },
    {
        "instance_id": "astropy__astropy-14182",
        "project": "astropy",
        "workspace": ".nexus/workspaces/astropy",
        "file": "astropy/coordinates/earth.py",
        "target_function": "get_gcrs_posvel",
        "task_family": "stable_local_edit",
    },
]

MODELS = {
    "nexus_anchor_7b": "qwen2.5-coder:7b",
    "nexus_anchor_14b": "qwen2.5-coder:14b-instruct-q3_K_M",
}


def read_file_content(workspace: str, filepath: str) -> str:
    """Read actual file content from workspace."""
    full_path = REPO_ROOT / workspace / filepath
    try:
        return full_path.read_text()
    except Exception:
        return ""


def find_function_context(content: str, func_name: str) -> str:
    """Find function context in file."""
    if not func_name:
        return content[:3000]
    lines = content.split("\n")
    start = None
    for i, line in enumerate(lines):
        if func_name in line and "def " in line:
            start = i
            break
    if start is None:
        return content[:3000]
    end = min(start + 50, len(lines))
    return "\n".join(lines[max(0, start - 5):end])


def build_anchored_prompt(task: dict, file_content: str) -> str:
    """Build prompt with actual source anchor."""
    func_context = find_function_context(file_content, task.get("target_function"))

    return f"""You are fixing a bug in {task['project']}.

FILE: {task['file']}
ACTUAL CURRENT SOURCE:
```python
{func_context}
```

The code above is the EXACT current content. Do NOT hallucinate or guess.

OUTPUT ONLY THE FIXED VERSION of the function/code block above.
Do NOT output SEARCH/REPLACE.
Do NOT output markdown fences.
Do NOT explain.
Output ONLY valid Python code that replaces the buggy section.

Fixed code:"""


def call_ollama(model: str, prompt: str, timeout: int = 120) -> dict:
    """Call Ollama."""
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
        }
    except Exception as e:
        return {"success": False, "output": "", "stderr": str(e), "latency_ms": 0}


def check_syntax(code: str) -> bool:
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False


def write_record(record: dict):
    RECORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RECORDS_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def run_single(task: dict, arm: str, model: str) -> dict:
    run_id = f"ANCHOR_{task['instance_id']}_{arm}_{int(time.time())}"

    file_content = read_file_content(task["workspace"], task["file"])
    if not file_content:
        return {"run_id": run_id, "error": "file_not_found", "solved": False}

    prompt = build_anchored_prompt(task, file_content)
    result = call_ollama(model, prompt)

    raw_hash = hashlib.sha256(result["output"].encode()).hexdigest() if result["output"] else ""
    syntax_ok = check_syntax(result["output"]) if result["success"] and result["output"] else False

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
        "source_anchor_used": True,
        "actual_source_in_prompt": True,
        "model_generated_SEARCH_detected": False,
        "raw_output_hash": raw_hash,
        "syntax_gate_passed": syntax_ok,
        "solved": False,
        "latency_ms": result["latency_ms"],
        "run_date": RUN_DATE,
    }

    write_record(record)
    return record


def main():
    print(f"=== Source Anchoring Fix Rerun ===")
    print(f"Tasks: {len(TASKS)}, Arms: {len(MODELS)}")
    print(f"Total: {len(TASKS) * len(MODELS)} runs")
    print()

    for task in TASKS:
        print(f"Task: {task['instance_id']}")
        for arm, model in MODELS.items():
            record = run_single(task, arm, model)
            syntax = record.get("syntax_gate_passed", False)
            print(f"  {arm}: syntax={syntax}")
        print()


if __name__ == "__main__":
    main()
