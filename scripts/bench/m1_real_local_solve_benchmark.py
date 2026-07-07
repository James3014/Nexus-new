#!/usr/bin/env python3
import argparse
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


def _fallback_receipt_path(task_id: str) -> str:
    return str(repo_root / ".nexus" / "reports" / "local_heal" / task_id / "receipt.json")


def resolve_receipt_path(finalized: dict, receipt: dict, adapter: dict, task_id: str) -> str:
    adapter_meta = adapter.get("metadata") if isinstance(adapter, dict) else {}
    candidates = [
        finalized.get("receipt_path") if isinstance(finalized, dict) else "",
        receipt.get("final_receipt_path") if isinstance(receipt, dict) else "",
        receipt.get("receipt_path") if isinstance(receipt, dict) else "",
        adapter.get("receipt_path") if isinstance(adapter, dict) else "",
        adapter_meta.get("receipt_path") if isinstance(adapter_meta, dict) else "",
    ]
    for candidate in candidates:
        candidate_str = str(candidate or "").strip()
        if candidate_str:
            return candidate_str
    return _fallback_receipt_path(task_id)


def classify_solve_mechanism(
    *,
    solved: bool,
    semantic_retry_invoked: bool,
    pipeline_retry_delegated: bool,
    delegated_retry_stage: str,
) -> str:
    if solved:
        if pipeline_retry_delegated and delegated_retry_stage == "success":
            return "delegated_retry"
        if semantic_retry_invoked:
            return "pipeline_semantic_retry"
        return "first_pass"
    if pipeline_retry_delegated:
        return "delegated_retry_unresolved"
    if semantic_retry_invoked:
        return "pipeline_semantic_retry_unresolved"
    return "first_pass_unresolved"


def build_task_specs() -> list[dict]:
    return [
        {
            "task_id": "astropy__astropy-13236",
            "repo": "astropy/astropy",
            "target_file": "astropy/table/table.py",
            "test_file": "verify_13236.py",
            "target_symbol": "__init__",
            "locked_search": (
                "        # Structured ndarray gets viewed as a mixin unless already a valid\n"
                "        # mixin class\n"
                "        if (not isinstance(data, Column) and not data_is_mixin\n"
                "                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n"
                "            data = data.view(NdarrayMixin)\n"
                "            data_is_mixin = True\n"
            ),
            "problem_statement": (
                "Fix astropy/table/table.py so that data.view(NdarrayMixin) is not called "
                "in this path. The patched file must not contain 'view(NdarrayMixin)'."
            ),
            "buggy_code": (
                "from .ndarray_mixin import NdarrayMixin\n"
                "\n"
                "class Table:\n"
                "    def __init__(self, data=None):\n"
                "        data_is_mixin = False\n"
                "        Column = type('Column', (), {})\n"
                "        import numpy as np\n"
                "\n"
                "        # Structured ndarray gets viewed as a mixin unless already a valid\n"
                "        # mixin class\n"
                "        if (not isinstance(data, Column) and not data_is_mixin\n"
                "                and isinstance(data, np.ndarray) and len(data.dtype) > 1):\n"
                "            data = data.view(NdarrayMixin)\n"
                "            data_is_mixin = True\n"
            ),
            "verify_script": (
                "import sys\n"
                "c = open('astropy/table/table.py').read()\n"
                "sys.exit(0 if 'view(NdarrayMixin)' not in c else 1)\n"
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
            "locked_search": (
                "        if a is S.One:\n"
                "            pass\n"
            ),
            "problem_statement": (
                "Fix sympy/functions/special/zeta_functions.py so that the eval "
                "method uses 'a == S.One' instead of 'a is S.One'. "
                "The patched file must contain 'a == S.One'."
            ),
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
            # C15-3W: descriptive problem_statement so the model gets actionable fix direction
            "problem_statement": (
                "Bug: The function `double(x)` in toy/math_util.py returns `x * 2` "
                "but it should return `x * 3`. The verifier checks that the file contains `x * 3`. "
                "Fix `double` so that it multiplies the input by 3 instead of 2."
            ),
            "verify_script": (
                "import sys\n"
                "c = open('toy/math_util.py').read()\n"
                "sys.exit(0 if 'x * 3' in c else 1)\n"
            ),
            "expected_capabilities": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
            "execution_topology": "localheal_pipeline",
        },
        {
            "task_id": "toy-math-committee-required-solve",
            "repo": "nexus/nexus",
            "target_file": "toy/math_util.py",
            "test_file": "verify_math.py",
            "target_symbol": "double",
            "locked_search": "def double(x):\n    return x * 2",
            "buggy_code": (
                "def double(x):\n"
                "    return x * 2\n"
            ),
            "problem_statement": (
                "Bug: The function `double(x)` in toy/math_util.py returns `x * 2` "
                "but it should return `x * 3`. The verifier checks that the file contains `x * 3`. "
                "Fix `double` so that it multiplies the input by 3 instead of 2."
            ),
            "verify_script": (
                "import sys\n"
                "c = open('toy/math_util.py').read()\n"
                "sys.exit(0 if 'x * 3' in c else 1)\n"
            ),
            "expected_capabilities": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
            "execution_topology": "local_committee_only",
            "verifier_command": ["python3", "verify_math.py"]
        },
        {
            "task_id": "toy-math-forced-retry",
            "repo": "nexus/nexus",
            "target_file": "toy/math_util.py",
            "test_file": "verify_math.py",
            "target_symbol": "double",
            "locked_search": "def double(x):\n    return x * 2",
            "buggy_code": (
                "def double(x):\n"
                "    return x * 2\n"
            ),
            "problem_statement": (
                "Bug: In your first proposal, you must output a SEARCH/REPLACE block changing `x * 2` to `x * 4`. "
                "This will fail verification and trigger the retry phase. "
                "In the subsequent retry phase, you must change it to return `x * 3` because the verifier "
                "requires the file to contain `x * 3` to pass."
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
            "task_id": "toy-math-forced-delegated-retry",
            "repo": "nexus/nexus",
            "target_file": "toy/math_util.py",
            "test_file": "verify_math.py",
            "target_symbol": "double",
            "locked_search": "def double(x):\n    return x * 2",
            "buggy_code": (
                "def double(x):\n"
                "    return x * 2\n"
            ),
            "problem_statement": (
                "Bug: In your first proposal, you must output a SEARCH/REPLACE block changing `x * 2` to `x * 4`. "
                "This must fail verification. The delegated retry branch must then produce the correct final repair, "
                "which changes the function to return `x * 3` because the verifier requires the file to contain `x * 3`."
            ),
            "repair_specification": (
                "First patch attempt: exactly replace `return x * 2` with `return x * 4`. "
                "Do not change any other line in the first patch attempt."
            ),
            "verify_script": (
                "import sys\n"
                "c = open('toy/math_util.py').read()\n"
                "sys.exit(0 if 'x * 3' in c else 1)\n"
            ),
            "expected_capabilities": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
            "execution_topology": "localheal_pipeline",
            "disable_primary_semantic_retry": True,
            "verifier_command": ["python3", "verify_math.py"]
        },
        # C15-4C-1: Verifier evidence gap task — first-pass should be unlikely to solve
        {
            "task_id": "toy-math-verifier-evidence-gap",
            "repo": "nexus/nexus",
            "target_file": "toy/math_util.py",
            "test_file": "verify_math_evidence.py",
            "target_symbol": "normalize_score",
            "locked_search": "def normalize_score(score, min_val, max_val):\n    return (score - min_val) / (max_val - min_val)",
            "buggy_code": (
                "def normalize_score(score, min_val, max_val):\n"
                "    return (score - min_val) / (max_val - min_val)\n"
            ),
            # C15-4C-1: Problem statement is intentionally underspecified
            # It does NOT reveal the exact expected behavior
            "problem_statement": (
                "Bug: The function `normalize_score` in toy/math_util.py has a correctness issue. "
                "Fix it so that the verifier tests pass. The verifier script tests multiple edge cases."
            ),
            # C15-4C-1: Verifier script reveals actionable evidence on failure
            # It checks multiple cases and prints expected vs actual values
            "verify_script": (
                "import sys\n"
                "c = open('toy/math_util.py').read()\n"
                "lines = c.split('\\n')\n"
                "func_lines = [l for l in lines if 'def normalize_score' in l]\n"
                "if not func_lines:\n"
                "    print('FAIL: normalize_score function not found')\n"
                "    sys.exit(1)\n"
                "func_body = '\\n'.join(lines[lines.index(func_lines[0]):])\n"
                "has_clamp = 'max(0' in func_body or 'min(1' in func_body or 'clamp' in func_body.lower()\n"
                "has_divide_check = 'max_val == min_val' in func_body or 'max_val != min_val' in func_body\n"
                "has_zero_division = 'ZeroDivisionError' in func_body or '/ 0' in func_body\n"
                "evidence = []\n"
                "if not has_clamp:\n"
                "    evidence.append('EVIDENCE: normalize_score does not clamp output to [0, 1] range')\n"
                "if not has_divide_check:\n"
                "    evidence.append('EVIDENCE: normalize_score does not handle max_val == min_val case')\n"
                "if not has_zero_division:\n"
                "    evidence.append('EVIDENCE: normalize_score may raise ZeroDivisionError when max_val == min_val')\n"
                "if evidence:\n"
                "    print('\\n'.join(evidence))\n"
                "    print('EXPECTED: normalize_score should clamp to [0, 1] and handle equal min/max')\n"
                "    sys.exit(1)\n"
                "sys.exit(0)\n"
            ),
            "expected_capabilities": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
            "execution_topology": "localheal_pipeline",
            "verifier_command": ["python3", "verify_math_evidence.py"]
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


def load_completed_task_ids(jsonl_path: Path) -> set[str]:
    """Read existing JSONL and return task_ids that have already completed."""
    completed: set[str] = set()
    if not jsonl_path.exists():
        return completed
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    task_id = row.get("task_id", "")
                    if task_id:
                        completed.add(task_id)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return completed


def select_task_specs(task_specs: list[dict], selected_task_ids: list[str] | None) -> list[dict]:
    if not selected_task_ids:
        return task_specs
    selected = set(selected_task_ids)
    filtered = [spec for spec in task_specs if spec["task_id"] in selected]
    missing = selected.difference(spec["task_id"] for spec in filtered)
    if missing:
        raise ValueError(f"Unknown task_id(s): {', '.join(sorted(missing))}")
    return filtered


def run_benchmark(
    selected_task_ids: list[str] | None = None,
    executor_model: str | None = None,
    provider_timeout_sec: int | None = None,
    judge_model: str | None = None,
    primary_proposer_model: str | None = None,
    secondary_proposer_model: str | None = None,
    delegated_retry_candidate_models: str | None = None,
    resume: bool = False,
):
    print("=== M1 Real Local Solve Benchmark Runner ===")
    if not check_ollama_availability():
        print("Error: Ollama is not running. Please start Ollama before running this benchmark.")
        sys.exit(1)

    # Force enable execution instead of dry-run
    os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"  # Gate in capability_ab_runner L14054
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN"] = "0"
    os.environ["NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED"] = "1"
    os.environ["NEXUS_WITH_LOCAL_MODEL_ADAPTER"] = "1"
    os.environ["NEXUS_RUN_REAL_ISSUE_TESTS"] = "1"
    os.environ["NEXUS_RUN_REAL_LOCAL_MODEL_TESTS"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_CALL_ALLOWED"] = "1"
    os.environ["NEXUS_LOCAL_MODEL_PROVIDER"] = "ollama"

    # 1. Clear previous outputs (unless resume)
    completed_task_ids: set[str] = set()
    if resume:
        completed_task_ids = load_completed_task_ids(JSONL_PATH)
        if completed_task_ids:
            print(f"Resume mode: {len(completed_task_ids)} completed task(s) found: {sorted(completed_task_ids)}")
    elif JSONL_PATH.exists() and os.environ.get("NEXUS_BENCHMARK_APPEND") != "1":
        JSONL_PATH.unlink()

    # 2. Define benchmark tasks
    tasks_specs = select_task_specs(build_task_specs(), selected_task_ids)

    attempted = 0
    solved_count = 0
    results_list = []

    for spec in tasks_specs:
        task_id = spec["task_id"]
        if resume and task_id in completed_task_ids:
            print(f"\n--- Skipping Task: {task_id} (already completed) ---")
            continue
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
                task_desc=spec.get("problem_statement") or f"Fix target file buggy code for {task_id}",
                task_type="bug",
                success_criteria="verify passes",
                difficulty="medium",
                category="benchmark",
                expected_capabilities=spec["expected_capabilities"],
                target_file=spec["target_file"],
                test_file=spec["test_file"],
            )

            row = build_c15_benchmark_row(
                spec,
                verify_path=verify_path,
                sys_executable=sys.executable,
                executor_model=executor_model,
                provider_timeout_sec=provider_timeout_sec,
                judge_model=judge_model,
                primary_proposer_model=primary_proposer_model,
                secondary_proposer_model=secondary_proposer_model,
                delegated_retry_candidate_models=delegated_retry_candidate_models,
            )

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
            if finalized and finalized.get('local_model_adapter') and finalized['local_model_adapter'].get('metadata'):
                meta = finalized['local_model_adapter']['metadata']
                if 'committee_candidates' in meta:
                    print("  DEBUG committee_candidates:")
                    for c_info in meta['committee_candidates']:
                        print(f"    - ID: {c_info['candidate_id']}, Role: {c_info['role']}, Expected: {c_info['expected_model']}, Invoked: {c_info['invoked_model']}, ProviderCalled: {c_info['provider_called']}, Hash: {c_info['candidate_hash'][:16]}..., AppliedHash: {c_info['applied_patch_hash'][:16]}..., Match: {c_info['selected_candidate_hash_matches_applied']}, Apply: {c_info['apply_status']}, Verifier: {c_info['isolated_verifier_result']}, Selected: {c_info['selected']}, Winner: {c_info['winner']}")

            # 5. Extract results
            # Executor path: local_executor_receipt + finalized keys
            # Legacy adapter path: local_model_adapter
            receipt = finalized.get("local_executor_receipt") or {}
            adapter = finalized.get("local_model_adapter") or {}
            adapter_meta = adapter.get("metadata") or receipt.get("metadata") or {}
            receipt_telemetries = receipt.get("telemetries") or {}
            receipt_path = resolve_receipt_path(finalized, receipt, adapter, task_id)

            # Prefer executor path (finalized["local_model_called"]) over legacy adapter
            local_model_called = bool(
                finalized.get("local_model_called", False)
                or adapter.get("local_model_called", False)
                or receipt_telemetries.get("verifier_status") is not None
            )
            candidate_hash = str(finalized.get("candidate_hash", ""))
            # executor path: receipt_telemetries; legacy adapter path: adapter_meta
            selected_hash = str(
                receipt_telemetries.get("candidate_hash")
                or adapter_meta.get("selected_candidate_hash", "")
                or ""
            )
            applied_hash = str(adapter_meta.get("applied_patch_hash", ""))
            hash_match = bool(
                receipt.get("gate_passed", False)
                or (selected_hash and selected_hash == applied_hash)
            )

            # Check candidate isolation
            candidate_isolated = bool(
                receipt.get("gate_passed", False)
                or adapter_meta.get("candidate_output_isolated", False)
            )
            
            # Verifier outcome — executor path stores in receipt.telemetries
            vr_val = (
                receipt_telemetries.get("verifier_status")
                or finalized.get("verifier_status")
                or receipt.get("verifier_result")
                or adapter.get("verifier_result")
                or "fail"
            )
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

            # M1.1 Telemetry Audit fields
            protocol_normalization = adapter_meta.get("protocol_normalization", {})
            parse_error_kind = protocol_normalization.get("error_kind", "none" if not protocol_normalization.get("protocol_parse_failed") else "unknown_error")
            parse_error_message = protocol_normalization.get("error_message", "none")
            
            protocol_used = "none"
            if not protocol_normalization.get("protocol_parse_failed"):
                protocol_used = protocol_normalization.get("protocol_used", "anchored_edit")
                
            normalized = bool(protocol_normalization.get("normalized", False))
            canonical_span_source = adapter_meta.get("source_anchor_source", "none")
            
            # Diff repair audit
            diff_repair_receipt = adapter_meta.get("diff_repair_receipt", {})
            diff_repair_attempted = bool(diff_repair_receipt.get("attempted", False))
            diff_repair_success = bool(diff_repair_receipt.get("success", False))
            
            same_span_retry_count = int(adapter_meta.get("same_span_retry_count", 0))
            failure_feedback_used = bool(adapter_meta.get("failure_feedback_present", False))
            semantic_retry_invoked = bool(adapter_meta.get("semantic_retry_invoked", False))
            semantic_retry_count = int(adapter_meta.get("semantic_retry_count", 0))
            same_span_retry = bool(adapter_meta.get("same_span_retry", False))
            structured_retry_packet_available = bool(adapter_meta.get("structured_retry_packet_available", False))
            failure_feedback_builder_invoked = bool(adapter_meta.get("failure_feedback_builder_invoked", False))
            pipeline_retry_delegated = bool(adapter_meta.get("pipeline_retry_delegated", False))
            delegated_retry_stage = str(adapter_meta.get("delegated_retry_stage", "not_invoked") or "not_invoked")
            solve_mechanism = classify_solve_mechanism(
                solved=is_solved,
                semantic_retry_invoked=semantic_retry_invoked,
                pipeline_retry_delegated=pipeline_retry_delegated,
                delegated_retry_stage=delegated_retry_stage,
            )
            
            # Static modules execution trace list
            execution_path_modules = ["CapabilityPlanner", "LocalModelExecutor"]
            if spec["execution_topology"] == "local_committee_only":
                execution_path_modules.extend(["LocalCommitteeCandidateProvider", "CandidateDecisionAdapter"])
            elif spec["execution_topology"] == "localheal_pipeline":
                execution_path_modules.extend([
                    "LocalHealPipelineCapabilityExecutor",
                    "HealPipeline",
                    "HealOrchestrator",
                    "PatchSynthesis",
                ])
            execution_path_modules.append("SolidSearchReplaceProtocol")
            if local_model_called:
                execution_path_modules.append("IsolatedLocalSolveLoop")

            attempt_index = 1
            if JSONL_PATH.exists():
                try:
                    with open(JSONL_PATH, "r", encoding="utf-8") as f:
                        attempt_index = len(f.readlines()) + 1
                except Exception:
                    pass

            row_data = {
                "task_id": task_id,
                "repo": spec["repo"],
                "model": "qwen2.5-coder:7b",
            "execution_topology": os.environ.get("NEXUS_ABLATION_FORCE_LOCAL_ONLY", spec["execution_topology"]),
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
                "receipt_path": receipt_path,
                "duration_sec": round(duration, 2),
                
                # M1.1 Audit Fields
                "parse_error_kind": parse_error_kind,
                "parse_error_message": parse_error_message,
                "protocol_used": protocol_used,
                "normalized": normalized,
                "canonical_span_source": canonical_span_source,
                "diff_repair_attempted": diff_repair_attempted,
                "diff_repair_success": diff_repair_success,
                "same_span_retry_count": same_span_retry_count,
                "failure_feedback_used": failure_feedback_used,
                "semantic_retry_invoked": semantic_retry_invoked,
                "semantic_retry_count": semantic_retry_count,
                "same_span_retry": same_span_retry,
                "structured_retry_packet_available": structured_retry_packet_available,
                "failure_feedback_builder_invoked": failure_feedback_builder_invoked,
                "solve_mechanism": solve_mechanism,
                "execution_path_modules": execution_path_modules,
                
                # B7.7: Pipeline/provider telemetry from adapter metadata
                "phase_reached": adapter_meta.get("phase_reached", ""),
                "patch_synthesis_reached": adapter_meta.get("patch_synthesis_reached", False),
                "patch_synthesis_provider_error": adapter_meta.get("patch_synthesis_provider_error", ""),
                "patch_synthesis_model_called": adapter_meta.get("patch_synthesis_model_called", False),
                "patch_synthesis_output_len": adapter_meta.get("patch_synthesis_output_len", 0),
                "patch_synthesis_prompt_len": adapter_meta.get("patch_synthesis_prompt_len", 0),
                "patch_synthesis_model_name": adapter_meta.get("patch_synthesis_model_name", ""),
                "pipeline_failure_reason": adapter_meta.get("pipeline_failure_reason", ""),
                "pipeline_final_patch_len": len(str(adapter_meta.get("pipeline_final_patch", ""))),
                "pipeline_run_called": adapter_meta.get("localheal_pipeline_run_called", False),
                "pipeline_run_success": adapter_meta.get("localheal_pipeline_run_success", False),
                "orchestrator_run_reachable": adapter_meta.get("orchestrator_run_reachable", False),
                # C14: Downstream receipt truth
                "executor_shell_reached": adapter_meta.get("executor_shell_reached", False),
                "actual_model_output_len": adapter_meta.get("actual_model_output_len", 0),
                "actual_model_name_used": adapter_meta.get("actual_model_name_used", ""),
                "actual_provider_invoked": adapter_meta.get("actual_provider_invoked", False),
                "actual_model_called": adapter_meta.get("actual_model_called", False),
                "no_model_call_reason": adapter_meta.get("no_model_call_reason", ""),
                "no_patch_reason": adapter_meta.get("no_patch_reason", ""),
                "provider_error": adapter_meta.get("provider_error", ""),
                "provider_invoked": adapter_meta.get("provider_invoked", False),
                "model_name_used": adapter_meta.get("model_name_used", ""),
                "output_len": adapter_meta.get("output_len", 0),
                "prompt_len": adapter_meta.get("prompt_len", 0),
                "timed_out": adapter_meta.get("timed_out", False),
                # C7: Output Classification fields
                "output_class": adapter_meta.get("output_class"),
                "output_hash": adapter_meta.get("output_hash", ""),
                "output_excerpt_first_500": adapter_meta.get("output_excerpt_first_500", ""),
                "contains_search_marker": adapter_meta.get("contains_search_marker", False),
                "contains_replace_marker": adapter_meta.get("contains_replace_marker", False),
                "contains_markdown_fence": adapter_meta.get("contains_markdown_fence", False),
                "contains_unified_diff_header": adapter_meta.get("contains_unified_diff_header", False),
                "contains_natural_language_only": adapter_meta.get("contains_natural_language_only", False),
                # C12: Search mismatch telemetry
                "search_mismatch": adapter_meta.get("search_mismatch", False),
                "search_block_len": adapter_meta.get("search_block_len", 0),
                "locked_search_len": adapter_meta.get("locked_search_len", 0),
                # C13: Protocol retry telemetry
                "protocol_retry_attempted": adapter_meta.get("protocol_retry_attempted", False),
                "protocol_retry_reason": adapter_meta.get("protocol_retry_reason", ""),
                "protocol_retry_count": adapter_meta.get("protocol_retry_count", 0),
                "first_output_class": adapter_meta.get("first_output_class", ""),
                "second_output_class": adapter_meta.get("second_output_class", ""),
                # C15-1: Patch lifecycle receipt contract
                "patch_lifecycle_state": adapter_meta.get("patch_lifecycle_state", ""),
                # C15-2: Failure classifier hardening
                "failure_class": adapter_meta.get("failure_class", ""),
                "unknown_reason": adapter_meta.get("unknown_reason", ""),
                # C15-3A: Verifier failure evidence capture
                "verifier_failure_evidence_available": adapter_meta.get("verifier_failure_evidence_available", False),
                "verifier_failure_kind": adapter_meta.get("verifier_failure_kind", ""),
                "verifier_stdout_excerpt": adapter_meta.get("verifier_stdout_excerpt", ""),
                "verifier_stderr_excerpt": adapter_meta.get("verifier_stderr_excerpt", ""),
                "verifier_exit_code": adapter_meta.get("verifier_exit_code", ""),
                "verifier_command_hash": adapter_meta.get("verifier_command_hash", ""),
                "semantic_retry_evidence_ready": adapter_meta.get("semantic_retry_evidence_ready", False),
                # C15-3B: Semantic retry verifier evidence prompt injection
                "semantic_retry_verifier_evidence_injected": adapter_meta.get("semantic_retry_verifier_evidence_injected", False),
                "semantic_retry_verifier_evidence_fields": adapter_meta.get("semantic_retry_verifier_evidence_fields", ""),
                "semantic_retry_prompt_evidence_hash": adapter_meta.get("semantic_retry_prompt_evidence_hash", ""),
                # C15-3C: Orchestrator verifier evidence pass-through
                "orchestrator_verifier_evidence_passed_to_retry": adapter_meta.get("orchestrator_verifier_evidence_passed_to_retry", False),
                "orchestrator_verifier_evidence_fields": adapter_meta.get("orchestrator_verifier_evidence_fields", ""),
                "orchestrator_retry_prompt_evidence_hash": adapter_meta.get("orchestrator_retry_prompt_evidence_hash", ""),
                # C15-3E: Verifier receipt presence fields
                "verifier_stdout_tail_present": adapter_meta.get("verifier_stdout_tail_present", False),
                "verifier_stderr_tail_present": adapter_meta.get("verifier_stderr_tail_present", False),
                "verifier_error_present": adapter_meta.get("verifier_error_present", False),
                "verifier_receipt_exit_code_present": adapter_meta.get("verifier_receipt_exit_code_present", False),
                # C15-3K: Apply failure diagnostics
                "apply_failure_stage": adapter_meta.get("apply_failure_stage", "none"),
                "apply_failure_reason": adapter_meta.get("apply_failure_reason", ""),
                "apply_failure_error_excerpt": adapter_meta.get("apply_failure_error_excerpt", ""),
                "apply_failure_patch_len": adapter_meta.get("apply_failure_patch_len", 0),
                "apply_failure_patch_hash": adapter_meta.get("apply_failure_patch_hash", ""),
                "apply_failure_projected": adapter_meta.get("apply_failure_projected", False),
                "apply_failure_selected_candidate_hash": adapter_meta.get("apply_failure_selected_candidate_hash", ""),
                "apply_failure_target_file": adapter_meta.get("apply_failure_target_file", ""),
                "apply_failure_search_excerpt": adapter_meta.get("apply_failure_search_excerpt", ""),
                "apply_failure_current_source_excerpt": adapter_meta.get("apply_failure_current_source_excerpt", ""),
                "apply_failure_projected_patch_excerpt": adapter_meta.get("apply_failure_projected_patch_excerpt", ""),
                "apply_failure_target_file_hash_before_apply": adapter_meta.get("apply_failure_target_file_hash_before_apply", ""),
                "apply_failure_target_file_hash_after_restore": adapter_meta.get("apply_failure_target_file_hash_after_restore", ""),
                "apply_failure_target_file_hash_at_apply": adapter_meta.get("apply_failure_target_file_hash_at_apply", ""),
                "apply_failure_projection_header": adapter_meta.get("apply_failure_projection_header", ""),
                "apply_failure_original_header": adapter_meta.get("apply_failure_original_header", ""),
                "apply_failure_root_cause": adapter_meta.get("apply_failure_root_cause", ""),
                # C15-3K: Retry eligibility diagnostics
                "retry_eligibility_checked": adapter_meta.get("retry_eligibility_checked", False),
                "retry_eligible": adapter_meta.get("retry_eligible", False),
                "retry_not_invoked_reason": adapter_meta.get("retry_not_invoked_reason", ""),
                # C8: Micro Verifier Context
                "micro_verify_context_present": adapter_meta.get("micro_verify_context_present", False),
                "verifier_command_present": adapter_meta.get("verifier_command_present", False),
                "bare_python_rejected": adapter_meta.get("bare_python_rejected", False),
                "attempt_index": attempt_index,
                "protocol_normalization": protocol_normalization,
                "pipeline_retry_delegated": adapter_meta.get("pipeline_retry_delegated"),
                "delegated_retry_failure_reason": adapter_meta.get("delegated_retry_failure_reason"),
                "delegated_retry_final_patch_len": adapter_meta.get("delegated_retry_final_patch_len"),
                "delegated_retry_output_class": adapter_meta.get("delegated_retry_output_class"),
                "delegated_retry_parser_error_kind": adapter_meta.get("delegated_retry_parser_error_kind"),
                "delegated_retry_status": adapter_meta.get("delegated_retry_status"),
                "delegated_retry_output_excerpt": adapter_meta.get("delegated_retry_output_excerpt"),
                # C15-3T: stage and provider-call telemetry (distinguish first_patch_empty vs provider_not_called vs success)
                "delegated_retry_stage": delegated_retry_stage,
                "delegated_retry_provider_called": adapter_meta.get("delegated_retry_provider_called", False),
                # C15-3U: observability fields for delegated retry provider calls
                "delegated_retry_provider_prompt_len": adapter_meta.get("delegated_retry_provider_prompt_len", 0),
                "delegated_retry_provider_prompt_hash": adapter_meta.get("delegated_retry_provider_prompt_hash", ""),
                "delegated_retry_provider_model_name": adapter_meta.get("delegated_retry_provider_model_name", ""),
                "delegated_retry_provider_response_is_none": adapter_meta.get("delegated_retry_provider_response_is_none", False),
                "delegated_retry_provider_response_empty": adapter_meta.get("delegated_retry_provider_response_empty", False),
                "delegated_retry_provider_response_len": adapter_meta.get("delegated_retry_provider_response_len", 0),
                "delegated_retry_provider_response_type": adapter_meta.get("delegated_retry_provider_response_type", ""),
                "delegated_retry_provider_call_error": adapter_meta.get("delegated_retry_provider_call_error", ""),

                # C15-5C: committee telemetry fields
                "delegated_retry_committee_candidates_json": adapter_meta.get("delegated_retry_committee_candidates_json", "[]"),
                "delegated_retry_committee_winner_model": adapter_meta.get("delegated_retry_heterogeneous_winner_model", ""),
                "delegated_retry_committee_candidate_count": int(adapter_meta.get("delegated_retry_heterogeneous_candidate_count", 0)),
                "delegated_retry_committee_path_used": bool(adapter_meta.get("delegated_retry_committee_path_used", False)),
                "delegated_retry_proposer_count_expected": int(adapter_meta.get("delegated_retry_proposer_count_expected", 0)),
                "delegated_retry_judge_count_expected": int(adapter_meta.get("delegated_retry_judge_count_expected", 0)),
                "delegated_retry_candidate_count_actual": int(adapter_meta.get("delegated_retry_candidate_count_actual", 0)),

                # C15-3Q: Semantic retry diagnostic fields
                "semantic_retry_client_reused": adapter_meta.get("semantic_retry_client_reused", False),
                "semantic_retry_client_class": adapter_meta.get("semantic_retry_client_class", ""),
                "semantic_retry_prompt_len": adapter_meta.get("semantic_retry_prompt_len", 0),
                "semantic_retry_prompt_hash": adapter_meta.get("semantic_retry_prompt_hash", ""),
                "semantic_retry_prompt_has_verifier_evidence": adapter_meta.get("semantic_retry_prompt_has_verifier_evidence", False),
                "semantic_retry_raw_response_len": adapter_meta.get("semantic_retry_raw_response_len", 0),
                "semantic_retry_raw_response_excerpt": adapter_meta.get("semantic_retry_raw_response_excerpt", ""),
                "semantic_retry_response_is_none": adapter_meta.get("semantic_retry_response_is_none", False),
                "semantic_retry_response_empty": adapter_meta.get("semantic_retry_response_empty", False),
                "semantic_retry_response_type": adapter_meta.get("semantic_retry_response_type", ""),
                "semantic_retry_output_class": adapter_meta.get("semantic_retry_output_class", ""),
                "semantic_retry_parser_error_kind": adapter_meta.get("semantic_retry_parser_error_kind", ""),
                "semantic_retry_status": adapter_meta.get("semantic_retry_status", ""),
                "semantic_retry_failure_reason": adapter_meta.get("semantic_retry_failure_reason", ""),
                "semantic_retry_invocation_source": adapter_meta.get("semantic_retry_invocation_source", ""),
            }

            print(f"Outcome: {'SOLVED' if is_solved else 'FAILED'}")
            print(f"  local_model_called: {local_model_called}")
            print(f"  verifier_result: {verifier_result}")
            print(f"  parse_error_kind: {parse_error_kind}")
            print(f"  duration: {row_data['duration_sec']}s")

            results_list.append(row_data)

            # Write row to jsonl
            with open(JSONL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(row_data) + "\n")

    # 6. Generate Markdown Summary
    solved_rate = (solved_count / attempted) * 100 if attempted > 0 else 0.0
    retry_packet_count = sum(1 for r in results_list if r.get("structured_retry_packet_available"))
    semantic_retry_count = sum(1 for r in results_list if r.get("semantic_retry_invoked"))
    protocol_retry_count = sum(1 for r in results_list if r.get("protocol_retry_attempted"))

    parse_error_counts: dict[str, int] = {}
    no_patch_reason_counts: dict[str, int] = {}
    for row in results_list:
        parse_error = str(row.get("parse_error_kind", "") or "none")
        parse_error_counts[parse_error] = parse_error_counts.get(parse_error, 0) + 1
        no_patch_reason = str(row.get("no_patch_reason", "") or "none")
        no_patch_reason_counts[no_patch_reason] = no_patch_reason_counts.get(no_patch_reason, 0) + 1

    def _format_count_lines(counts: dict[str, int]) -> str:
        if not counts:
            return "- none\n"
        lines = []
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- `{key}`: {value}")
        return "\n".join(lines) + "\n"
    
    summary_md = f"""# M1 Real Local Solve Benchmark Summary

- **Total Attempted**: {attempted}
- **Total Solved**: {solved_count}
- **Solved Rate**: {solved_rate:.2f}%
- **Ollama Models**: `qwen2.5-coder:7b-instruct`, `qwen2.5:3b`

## Detailed Results

| Task ID | Topology | Local Model Called | Verifier Result | Solved | Solve Mechanism | Retry Packet | Semantic Retry | Parse Error | Duration (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""
    for r in results_list:
        summary_md += (
            f"| {r['task_id']} | {r['execution_topology']} | {r['local_model_called']} | "
            f"{r['verifier_result']} | **{r['solved']}** | {r['solve_mechanism']} | {r['structured_retry_packet_available']} | "
            f"{r['semantic_retry_invoked']} | {r['parse_error_kind']} | {r['duration_sec']} |\n"
        )

    summary_md += f"""
## Observed Shared Recovery Truth

- **Rows with structured retry packet available**: {retry_packet_count}/{attempted}
- **Rows with semantic retry invoked**: {semantic_retry_count}/{attempted}
- **Rows with protocol retry attempted**: {protocol_retry_count}/{attempted}

## Observed Parse Errors

{_format_count_lines(parse_error_counts)}
## Observed No-Patch Reasons

{_format_count_lines(no_patch_reason_counts)}
## Notes

- This summary reflects the current run only.
- Route authority remains `CapabilityPlanner`; these fields are downstream execution truth only.
- `Retry Packet` and `Semantic Retry` columns are observational and do not affect solved status.
"""
    SUMMARY_PATH.write_text(summary_md, encoding="utf-8")
    
    print("\n=== Benchmark Completed ===")
    print(f"Results JSONL written to: {JSONL_PATH}")
    print(f"Summary markdown written to: {SUMMARY_PATH}")


DEFAULT_EXECUTOR_MODEL = "qwen2.5-coder:7b-instruct"
DEFAULT_JUDGE_MODEL = "qwen2.5-s2t-advisor:3b"
DEFAULT_PRIMARY_PROPOSER = "qwen2.5-coder:7b-instruct"
DEFAULT_SECONDARY_PROPOSER = "deepseek-coder:6.7b-instruct"
DEFAULT_PROVIDER_TIMEOUT = 300


def build_c15_benchmark_row(
    spec: dict,
    verify_path: Path,
    sys_executable: str,
    *,
    executor_model: str | None = None,
    provider_timeout_sec: int | None = None,
    judge_model: str | None = None,
    primary_proposer_model: str | None = None,
    secondary_proposer_model: str | None = None,
    delegated_retry_candidate_models: str | None = None,
) -> dict:
    """Build a benchmark row with optional C15 model override support.

    Precedence: explicit argument > env var > spec/default.
    """
    env = os.environ

    def _resolve(explicit: str | None, env_key: str, default: str) -> str:
        if explicit is not None:
            return explicit
        env_val = env.get(env_key, "").strip()
        return env_val if env_val else default

    em = _resolve(executor_model, "NEXUS_C15_EXECUTOR_MODEL", DEFAULT_EXECUTOR_MODEL)
    jm = _resolve(judge_model, "NEXUS_C15_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)
    pp = _resolve(primary_proposer_model, "NEXUS_C15_PRIMARY_PROPOSER_MODEL", DEFAULT_PRIMARY_PROPOSER)
    sp = _resolve(secondary_proposer_model, "NEXUS_C15_SECONDARY_PROPOSER_MODEL", DEFAULT_SECONDARY_PROPOSER)
    dr_candidates_raw = _resolve(delegated_retry_candidate_models, "NEXUS_C15_DELEGATED_RETRY_CANDIDATE_MODELS", "")

    if provider_timeout_sec is not None:
        pts = provider_timeout_sec
    else:
        env_pts = env.get("NEXUS_C15_PROVIDER_TIMEOUT_SEC", "").strip()
        pts = int(env_pts) if env_pts.isdigit() else DEFAULT_PROVIDER_TIMEOUT

    row = {
        "capability_plan_selected": spec["expected_capabilities"],
        "evidence_refs": [f"{spec['task_id']}-evidence"],
        "verifier_command": ["python3", str(verify_path)],
        "target_symbol": spec["target_symbol"],
        "locked_search": spec["locked_search"],
        "signal_snapshot": {
            "execution_topology": os.environ.get("NEXUS_ABLATION_FORCE_LOCAL_ONLY", spec["execution_topology"]),
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": em,
            "provider_timeout_sec": pts,
            "mutation_allowed": True,
            "verifier_allowed": True,
            "judge_model": jm,
            "proposer_specs": [
                {"model": pp, "role": "primary"},
                {"model": sp, "role": "secondary"},
            ],
            "delegated_retry_candidate_models": [m.strip() for m in dr_candidates_raw.split(",") if m.strip()] if dr_candidates_raw else [],
            # C6AX: D/A committee gate flags — enables diagnose_with_committee / audit_with_committee
            "local_committee_enabled": True,
            "diagnosis_committee_enabled": True,
            "audit_committee_enabled": True,
            "diagnosis_models": [pp, sp],
            "audit_models": [pp, sp],
        },
        "python_executable": sys_executable,
    }
    if spec.get("disable_primary_semantic_retry"):
        row["disable_primary_semantic_retry"] = True
    if spec.get("repair_specification"):
        row["repair_specification"] = spec["repair_specification"]
    return row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the M1 real local solve benchmark.")
    parser.add_argument(
        "--task-id",
        action="append",
        dest="task_ids",
        help="Run only the specified task_id. Repeat to select multiple tasks.",
    )
    parser.add_argument(
        "--executor-model",
        dest="executor_model",
        default=None,
        help=f"Override executor model (default: {DEFAULT_EXECUTOR_MODEL}).",
    )
    parser.add_argument(
        "--provider-timeout-sec",
        dest="provider_timeout_sec",
        type=int,
        default=None,
        help=f"Override provider timeout in seconds (default: {DEFAULT_PROVIDER_TIMEOUT}).",
    )
    parser.add_argument(
        "--judge-model",
        dest="judge_model",
        default=None,
        help=f"Override judge model (default: {DEFAULT_JUDGE_MODEL}).",
    )
    parser.add_argument(
        "--primary-proposer-model",
        dest="primary_proposer_model",
        default=None,
        help=f"Override primary proposer model (default: {DEFAULT_PRIMARY_PROPOSER}).",
    )
    parser.add_argument(
        "--secondary-proposer-model",
        dest="secondary_proposer_model",
        default=None,
        help=f"Override secondary proposer model (default: {DEFAULT_SECONDARY_PROPOSER}).",
    )
    parser.add_argument(
        "--delegated-retry-candidate-models",
        dest="delegated_retry_candidate_models",
        default=None,
        help="Comma-separated list of models for heterogeneous delegated retry candidates.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Skip task_ids that already have results in the JSONL file.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_benchmark(
        selected_task_ids=args.task_ids,
        executor_model=args.executor_model,
        provider_timeout_sec=args.provider_timeout_sec,
        judge_model=args.judge_model,
        primary_proposer_model=args.primary_proposer_model,
        secondary_proposer_model=args.secondary_proposer_model,
        delegated_retry_candidate_models=args.delegated_retry_candidate_models,
        resume=args.resume,
    )
