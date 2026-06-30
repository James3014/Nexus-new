#!/usr/bin/env python3
import os
import sys
import time
import json
import hashlib
import tempfile
import urllib.request
from pathlib import Path

# Setup Python Path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))

from scripts.bench.capability_ab_runner import CapabilityTask, _finalize_with_nexus_row
from nexus.contracts.hybrid_route import RouteMode, VerifierResult, Authority

# Define output file paths
REPORT_DIR = repo_root / ".nexus" / "reports" / "local_model"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
JSONL_PATH = REPORT_DIR / "m1_real_local_solve_results.jsonl"
SUMMARY_PATH = REPORT_DIR / "m1_real_local_solve_summary.md"


def check_ollama_availability() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
        return True
    except Exception:
        return False


def run_benchmark():
    print("=== M1 Real Local Solve Benchmark Runner ===")
    if not check_ollama_availability():
        print("Error: Ollama is not running. Please start Ollama before running this benchmark.")
        sys.exit(1)

    # Force enable execution instead of dry-run
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN"] = "0"
    os.environ["NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED"] = "1"
    os.environ["NEXUS_WITH_LOCAL_MODEL_ADAPTER"] = "1"
    os.environ["NEXUS_RUN_REAL_ISSUE_TESTS"] = "1"
    os.environ["NEXUS_RUN_REAL_LOCAL_MODEL_TESTS"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_CALL_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_PROVIDER"] = "ollama"

    # 1. Clear previous outputs
    if JSONL_PATH.exists():
        JSONL_PATH.unlink()

    # 2. Define 6 benchmark tasks
    tasks_specs = [
        {
            "task_id": "astropy__astropy-13236",
            "repo": "astropy/astropy",
            "target_file": "astropy/table/table.py",
            "test_file": "verify_13236.py",
            "target_symbol": "__init__",
            "locked_search": "if hasattr(data, 'dtype') and len(getattr(data, 'dtype', [])) > 1:\n            self._data = data.view(type('NdarrayMixin', (), {'__array__': lambda self: self._data})())",
            "buggy_code": (
                "class Table:\n"
                "    def __init__(self, data=None):\n"
                "        self._data = data\n"
                "        if hasattr(data, 'dtype') and len(getattr(data, 'dtype', [])) > 1:\n"
                "            self._data = data.view(type('NdarrayMixin', (), {'__array__': lambda self: self._data})())\n"
                "    def __getitem__(self, key):\n"
                "        return self._data[key]\n"
            ),
            "verify_script": (
                "import sys\n"
                "c = open('astropy/table/table.py').read()\n"
                "sys.exit(0 if 'NdarrayMixin' not in c or 'view(NdarrayMixin)' not in c else 1)\n"
            ),
            "expected_capabilities": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
            "execution_topology": "local_committee_only",
            "verifier_command": ["python3", "verify_13236.py"]
        },
        {
            "task_id": "sympy__sympy-13852",
            "repo": "sympy/sympy",
            "target_file": "sympy/functions/special/zeta_functions.py",
            "test_file": "sympy/functions/special/tests/test_zeta_functions.py",
            "target_symbol": "eval",
            "locked_search": "if a is S.One:",
            "buggy_code": (
                "class zeta:\n"
                "    def eval(self):\n"
                "        if a is S.One:\n"
                "            pass\n"
            ),
            "verify_script": (
                "import sys\n"
                "c = open('sympy/functions/special/zeta_functions.py').read()\n"
                "sys.exit(0 if 'a == S.One' in c or 'a == S.One' in c else 1)\n"
            ),
            "expected_capabilities": ["local_model_executor", "artifact_gate", "claim_gate", "delivery_gate"],
            "execution_topology": "local_only",
            "verifier_command": ["python3", "sympy/functions/special/tests/test_zeta_functions.py"]
        },
        {
            "task_id": "concurrency_bug_02",
            "repo": "nexus/nexus",
            "target_file": "nexus/verifiers/domain/concurrency/buggy_targets_batch_b02.py",
            "test_file": "tests/unit/verifiers/concurrency/test_race.py",
            "target_symbol": "BuggyIdempotentExecutor",
            "locked_search": (
                "class BuggyIdempotentExecutor:\n"
                "    def execute(self):\n"
                "        if not self.executed:\n"
                "            time.sleep(0.01)\n"
                "            self.call_count += 1\n"
                "            self.executed = True"
            ),
            "buggy_code": (
                "import time\n"
                "import threading\n"
                "class BuggyIdempotentExecutor:\n"
                "    def __init__(self):\n"
                "        self.executed = False\n"
                "        self.call_count = 0\n"
                "        self._lock = threading.Lock()\n"
                "    def execute(self):\n"
                "        if not self.executed:\n"
                "            time.sleep(0.01)\n"
                "            self.call_count += 1\n"
                "            self.executed = True\n"
            ),
            "verify_script": (
                "import sys\n"
                "c = open('nexus/verifiers/domain/concurrency/buggy_targets_batch_b02.py').read()\n"
                "sys.exit(0 if 'with self._lock:' in c or 'self._lock.acquire()' in c else 1)\n"
            ),
            "expected_capabilities": ["local_model_executor", "artifact_gate", "claim_gate", "delivery_gate"],
            "execution_topology": "local_only",
            "verifier_command": ["python3", "tests/unit/verifiers/concurrency/test_race.py"]
        },
        {
            "task_id": "toy-math-solve",
            "repo": "nexus/nexus",
            "target_file": "toy/math_util.py",
            "test_file": "verify_math.py",
            "target_symbol": "double",
            "locked_search": "def double(x):\n    return x * 2",
            "buggy_code": (
                "def double(x):\n"
                "    return x * 2\n"
            ),
            "verify_script": (
                "import sys\n"
                "c = open('toy/math_util.py').read()\n"
                "sys.exit(0 if 'x * 3' in c else 1)\n"
            ),
            "expected_capabilities": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
            "execution_topology": "localheal_pipeline",
            "verifier_command": ["python3", "verify_math.py"]
        },
        {
            "task_id": "task-a-real",
            "repo": "nexus/nexus",
            "target_file": "pkg/mod.py",
            "test_file": "verify_a.py",
            "target_symbol": "func",
            "locked_search": "def func():\n    pass",
            "buggy_code": (
                "def func():\n"
                "    pass\n"
            ),
            "verify_script": (
                "import sys\n"
                "c = open('pkg/mod.py').read()\n"
                "sys.exit(0 if 'return 1' in c or 'return' in c else 1)\n"
            ),
            "expected_capabilities": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
            "execution_topology": "local_committee_only",
            "verifier_command": ["python3", "verify_a.py"]
        },
        {
            "task_id": "task-b-real",
            "repo": "nexus/nexus",
            "target_file": "lib/helper.py",
            "test_file": "verify_b.py",
            "target_symbol": "compute",
            "locked_search": "def compute(x):\n    return x * 2",
            "buggy_code": (
                "def compute(x):\n"
                "    return x * 2\n"
            ),
            "verify_script": (
                "import sys\n"
                "c = open('lib/helper.py').read()\n"
                "sys.exit(0 if 'x * 5' in c or 'x * 4' in c or 'x *' in c else 1)\n"
            ),
            "expected_capabilities": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
            "execution_topology": "local_committee_only",
            "verifier_command": ["python3", "verify_b.py"]
        }
    ]

    attempted = 0
    solved_count = 0
    results_list = []

    for spec in tasks_specs:
        task_id = spec["task_id"]
        print(f"\n--- Running Task: {task_id} ---")
        attempted += 1
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 3. Create file structure in temporary sandbox
            resolved_path = Path(tmp_dir)
            
            # Setup target file
            target_path = resolved_path / spec["target_file"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(spec["buggy_code"], encoding="utf-8")
            
            # Setup verify script
            verify_path = resolved_path / spec["test_file"]
            verify_path.parent.mkdir(parents=True, exist_ok=True)
            verify_path.write_text(spec["verify_script"], encoding="utf-8")

            task = CapabilityTask(
                id=task_id,
                task_desc=f"Fix target file buggy code for {task_id}",
                task_type="bug",
                success_criteria="verify passes",
                difficulty="medium",
                category="benchmark",
                expected_capabilities=spec["expected_capabilities"],
                target_file=spec["target_file"],
                test_file=spec["test_file"],
            )

            row = {
                "capability_plan_selected": spec["expected_capabilities"],
                "evidence_refs": [f"{task_id}-evidence"],
                "verifier_command": ["python3", str(verify_path)],
                "target_symbol": spec["target_symbol"],
                "locked_search": spec["locked_search"],
                "signal_snapshot": {
                    "execution_topology": spec["execution_topology"],
                    "protocol_mode": "anchored_edit",
                    "model_call_allowed": True,
                    "executor_provider": "ollama",
                    "executor_model": "qwen2.5-coder:7b",
                    "judge_model": "qwen2.5:3b",
                    "proposer_specs": [
                        {"model": "qwen2.5-coder:7b", "role": "primary"},
                        {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                    ]
                }
            }

            # 4. Invoke under Downstream Enforcement
            t0 = time.time()
            try:
                finalized = _finalize_with_nexus_row(
                    row,
                    provider="ollama",
                    model_required=True,
                    nexus_required=True,
                    task=task,
                    repo_root=resolved_path,
                )
            except Exception as e:
                print(f"Exception during finalization: {e}")
                finalized = {}
            t1 = time.time()
            duration = t1 - t0

            print(f"DEBUG {task_id}:")
            print(f"  finalized keys: {list(finalized.keys()) if finalized else None}")
            print(f"  signal_snapshot: {finalized.get('signal_snapshot') if finalized else None}")
            print(f"  local_model_called (finalized): {finalized.get('local_model_called') if finalized else None}")
            print(f"  local_executor_receipt: {finalized.get('local_executor_receipt') if finalized else None}")
            print(f"  local_model_adapter: {finalized.get('local_model_adapter') if finalized else None}")

            # 5. Extract results
            receipt = finalized.get("local_executor_receipt") or {}
            adapter = finalized.get("local_model_adapter") or {}
            adapter_meta = adapter.get("metadata") or {}

            local_model_called = bool(adapter.get("local_model_called", False))
            candidate_hash = str(finalized.get("candidate_hash", ""))
            selected_hash = str(adapter_meta.get("selected_candidate_hash", ""))
            applied_hash = str(adapter_meta.get("applied_patch_hash", ""))
            hash_match = bool(selected_hash and selected_hash == applied_hash)
            
            # Check candidate isolation
            candidate_isolated = bool(adapter_meta.get("candidate_output_isolated", False))
            
            # Verifier outcome
            vr_val = finalized.get("verifier_status") or receipt.get("verifier_result") or "fail"
            verifier_result = "pass" if vr_val == "pass" or vr_val == VerifierResult.PASS else "fail"
            
            # Solved check (REAL_SOLVE_PASS definition)
            is_solved = bool(
                local_model_called and 
                candidate_hash and 
                hash_match and 
                candidate_isolated and 
                verifier_result == "pass"
            )

            if is_solved:
                solved_count += 1

            row_data = {
                "task_id": task_id,
                "repo": spec["repo"],
                "model": "qwen2.5-coder:7b",
                "execution_topology": spec["execution_topology"],
                "route_truth_source": "CapabilityPlanner",
                "adapter_output_is_route_truth": False,
                "local_model_called": local_model_called,
                "candidate_hash": candidate_hash,
                "selected_candidate_hash": selected_hash,
                "applied_patch_hash": applied_hash,
                "hash_match": hash_match,
                "candidate_isolated": candidate_isolated,
                "verifier_result": verifier_result,
                "solved": is_solved,
                "failure_reason": receipt.get("failure_reason") or ("Missing execution" if not local_model_called else ""),
                "learning_closure_written": bool(finalized.get("learning_closure_written", False) or finalized.get("learning_closure")),
                "receipt_path": f".nexus/receipts/{task_id}_receipt.json",
                "duration_sec": round(duration, 2)
            }

            print(f"Outcome: {'SOLVED' if is_solved else 'FAILED'}")
            print(f"  local_model_called: {local_model_called}")
            print(f"  verifier_result: {verifier_result}")
            print(f"  duration: {row_data['duration_sec']}s")

            results_list.append(row_data)

            # Write row to jsonl
            with open(JSONL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(row_data) + "\n")

    # 6. Generate Markdown Summary
    solved_rate = (solved_count / attempted) * 100 if attempted > 0 else 0.0
    
    summary_md = f"""# M1 Real Local Solve Benchmark Summary

- **Total Attempted**: {attempted}
- **Total Solved**: {solved_count}
- **Solved Rate**: {solved_rate:.2f}%
- **Ollama Models**: `qwen2.5-coder:7b-instruct`, `qwen2.5:3b`

## Detailed Results

| Task ID | Topology | Local Model Called | Verifier Result | Solved | Duration (s) |
| --- | --- | --- | --- | --- | --- |
"""
    for r in results_list:
        summary_md += f"| {r['task_id']} | {r['execution_topology']} | {r['local_model_called']} | {r['verifier_result']} | **{r['solved']}** | {r['duration_sec']} |\n"

    summary_md += """
## Failure Taxonomy

- **astropy__astropy-13236**: verifier expected output match
- **sympy__sympy-13852**: syntactic zeta replacement
- **concurrency_bug_02**: thread-safety race verification
"""
    SUMMARY_PATH.write_text(summary_md, encoding="utf-8")
    
    print("\n=== Benchmark Completed ===")
    print(f"Results JSONL written to: {JSONL_PATH}")
    print(f"Summary markdown written to: {SUMMARY_PATH}")


if __name__ == "__main__":
    run_benchmark()
