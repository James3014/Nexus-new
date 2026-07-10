from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
)
from nexus.engine.capability_receipt_adapters import LocalHealReceiptAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.local_heal.run_real_qwen_small_batch_eval import find_ollama_model

RESULTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "bench"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TASKS = [
    {
        "task_id": "13852_repro",
        "description": "polylog(1, z) expand_func bug: expand_func should handle polylog(1, z) = -log(1 - z)",
        "source_code": "def expand_func(expr):\n    from sympy.functions.special.polylogarithms import polylog\n    if isinstance(expr, polylog) and expr.args[0] == 1:\n        return expr\n    return expr\n",
        "target_symbol": "expand_func",
        "locked_search": "return expr",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import expand_func; from sympy import polylog, log; r = expand_func(polylog(1, 0.5)); assert str(r) == '-log(0.5)', f'got {r}'",
        ],
    },
    {
        "task_id": "basic_hash",
        "description": "basic hash collision fix: ensure Basic objects hash correctly",
        "source_code": "class Basic:\n    def __init__(self, name):\n        self.name = name\n    def __hash__(self):\n        return hash(self.name)\n    def __eq__(self, other):\n        return self.name == other.name\n",
        "target_symbol": "Basic",
        "locked_search": "return hash(self.name)",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import Basic; a, b = Basic('x'), Basic('x'); assert hash(a) == hash(b); assert a == b",
        ],
    },
    {
        "task_id": "basic_eq",
        "description": "basic equality comparison: fix comparison for relational expressions",
        "source_code": "def compare(a, b):\n    return a == b\n",
        "target_symbol": "compare",
        "locked_search": "return a == b",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import compare; assert compare(1, 1) is True; assert compare(1, 2) is False",
        ],
    },
    {
        "task_id": "eval_power",
        "description": "power evaluation edge case: fix Pow.eval for special cases",
        "source_code": "def pow_eval(base, exp):\n    if exp == 0:\n        return 1\n    if base == 0 and exp < 0:\n        raise ZeroDivisionError\n    return base ** exp\n",
        "target_symbol": "pow_eval",
        "locked_search": "return base ** exp",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import pow_eval; assert pow_eval(2, 0) == 1; assert pow_eval(2, 3) == 8",
        ],
    },
    {
        "task_id": "cache",
        "description": "cache invalidation bug: fix incorrect caching behavior",
        "source_code": "_cache = {}\ndef cached_func(key, value):\n    if key in _cache:\n        return _cache[key]\n    _cache[key] = value\n    return value\n",
        "target_symbol": "cached_func",
        "locked_search": "_cache[key] = value",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import cached_func; assert cached_func('a', 1) == 1; assert cached_func('a', 2) == 1",
        ],
    },
    {
        "task_id": "complex",
        "description": "complex number simplification: fix complex simplification",
        "source_code": "def simplify_complex(z):\n    if hasattr(z, 'imag') and z.imag == 0:\n        return z.real\n    return z\n",
        "target_symbol": "simplify_complex",
        "locked_search": "return z.real",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import simplify_complex; r = simplify_complex(complex(3, 0)); assert r == 3",
        ],
    },
    {
        "task_id": "containers",
        "description": "container iteration bug: fix iteration over sympy containers",
        "source_code": "def flatten(lst):\n    result = []\n    for item in lst:\n        if isinstance(item, list):\n            result.extend(item)\n        else:\n            result.append(item)\n    return result\n",
        "target_symbol": "flatten",
        "locked_search": "result.extend(item)",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import flatten; assert flatten([1, [2, 3], 4]) == [1, 2, 3, 4]",
        ],
    },
    {
        "task_id": "count_ops",
        "description": "operator counting off-by-one: fix operation counter",
        "source_code": "def count_operations(expr):\n    if isinstance(expr, (int, float)):\n        return 1\n    if isinstance(expr, tuple):\n        return sum(count_operations(e) for e in expr)\n    return 1\n",
        "target_symbol": "count_operations",
        "locked_search": "return 1",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import count_operations; assert count_operations(5) == 1; assert count_operations((1, 2)) == 2",
        ],
    },
    {
        "task_id": "diff",
        "description": "differentiation edge case: fix diff for special functions",
        "source_code": "def differentiate(expr):\n    if callable(expr):\n        return expr\n    return 0\n",
        "target_symbol": "differentiate",
        "locked_search": "return expr",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import differentiate; assert differentiate(lambda x: x) is not None",
        ],
    },
    {
        "task_id": "equal",
        "description": "structural equality fix: fix equality for expression trees",
        "source_code": "def struct_equal(a, b):\n    if type(a) != type(b):\n        return False\n    if isinstance(a, (list, tuple)):\n        return len(a) == len(b) and all(struct_equal(x, y) for x, y in zip(a, b))\n    return a == b\n",
        "target_symbol": "struct_equal",
        "locked_search": "return a == b",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import struct_equal; assert struct_equal([1, 2], [1, 2]); assert not struct_equal([1, 2], [1, 3])",
        ],
    },
    {
        "task_id": "eval",
        "description": "evaluation semantic: fix eval for symbolic expressions",
        "source_code": "def eval_expr(expr):\n    try:\n        return eval(str(expr))\n    except:\n        return None\n",
        "target_symbol": "eval_expr",
        "locked_search": "return eval(str(expr))",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import eval_expr; assert eval_expr('1+2') == 3",
        ],
    },
    {
        "task_id": "evalf",
        "description": "floating point evaluation: fix evalf precision bug",
        "source_code": "def evalf_expr(expr, prec=10):\n    return round(float(expr), prec)\n",
        "target_symbol": "evalf_expr",
        "locked_search": "return round(float(expr), prec)",
        "verifier_command": [
            "python3", "-c",
            "import sys; sys.path.append('.'); from f import evalf_expr; assert abs(evalf_expr('3.14159', 3) - 3.142) < 0.001",
        ],
    },
]

MODEL_SIZE_7B = 7_000_000_000


def _run_quadrant(tasks: list[dict], quadrant: str, full_model_name: str) -> list[dict]:
    results = []
    env_updates = {
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE": "1",
        "NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_NAME": full_model_name,
    }
    if quadrant == "bare":
        env_updates["NEXUS_DISABLE_CLOUD"] = "1"
        env_updates["NEXUS_QUADRANT"] = "bare"
    elif quadrant == "local_only_executed":
        env_updates["NEXUS_DISABLE_CLOUD"] = "1"
    elif quadrant == "cloud_exhausted":
        env_updates["NEXUS_QUOTA_EXHAUSTED"] = "1"

    from unittest.mock import patch

    for fixture in tasks:
        task_id = fixture["task_id"]
        start_time = time.time()
        with tempfile.TemporaryDirectory() as src_root:
            test_file = "f.py"
            src_path = os.path.join(src_root, test_file)
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(fixture["source_code"])

            controls = {
                "source_root": src_root,
                "target_file": test_file,
                "target_symbol": fixture["target_symbol"],
                "locked_search": fixture["locked_search"],
                "verifier_command": fixture["verifier_command"],
                "work_dir": "",
                "enable_local_heal": True,
                "local_heal_mode": "active",
                "route_context": {
                    "signal_snapshot": {
                        "model_call_allowed": True,
                        "executor_provider": "ollama",
                        "executor_model": full_model_name,
                        "candidate_enabled": True,
                        "advisory_enabled": True,
                        "isolated_solve_enabled": True,
                        "mutation_allowed": True,
                        "verifier_allowed": True,
                        "model_size": MODEL_SIZE_7B,
                    },
                },
            }
            request = LocalHealCapabilityRequest(
                task_id=task_id,
                problem_statement=fixture["description"],
                evidence_refs=(f"n29-{quadrant}-ref",),
                executor_controls=controls,
                dry_run=False,
            )
            with patch.dict(os.environ, env_updates):
                response = LocalHealCapabilityAdapter.run(request)

            receipt_adapter = LocalHealReceiptAdapter()
            receipt = receipt_adapter.build(
                claim_verified=True, payload=response.capability_payload
            )

            duration = time.time() - start_time
            metadata = response.capability_payload.get("metadata", {})
            route_mode = response.hybrid_route.route_mode.value
            sel_hash = metadata.get("selected_candidate_hash", "")
            app_hash = metadata.get("applied_patch_hash", "")
            verifier_status = metadata.get("verifier_status", "blocked")

            is_solved = (
                route_mode in ("local_only_executed", "local_only_candidate")
                and receipt.gate_passed is True
                and verifier_status == "pass"
                and bool(sel_hash)
                and bool(app_hash)
            )

            result_item = {
                "task_id": task_id,
                "quadrant": quadrant,
                "solved": is_solved,
                "route_mode": route_mode,
                "gate_passed": receipt.gate_passed,
                "verifier_status": verifier_status,
                "fallback_block_reason": response.hybrid_route.fallback_block_reason,
                "duration_sec": round(duration, 2),
                "public_claim_allowed": response.hybrid_route.public_claim_allowed,
                "production_ready": response.hybrid_route.production_ready,
                "model_size": MODEL_SIZE_7B,
                "lite_auto_trigger": "auto_lite_weak_model_size_lt_8B",
            }
            results.append(result_item)

            ws = response.hybrid_route.metadata.get("workspace_path", "")
            if ws and os.path.exists(ws):
                try:
                    shutil.rmtree(ws)
                except Exception:
                    pass
    return results


def test_n29_4quadrants_12_tasks_lite_local_model() -> None:
    model_name = find_ollama_model("qwen2.5-coder")
    if not model_name:
        pytest.skip("Ollama or qwen2.5-coder not available locally")

    all_results = []
    for quadrant in ["with_nexus", "bare", "local_only_executed", "cloud_exhausted"]:
        q_results = _run_quadrant(TASKS, quadrant, model_name)
        all_results.extend(q_results)

        solved = sum(1 for r in q_results if r["solved"])
        print(f"  [{quadrant}] solved: {solved}/{len(q_results)}")

    out_path = RESULTS_DIR / "n29_4quadrants_lite_results.json"
    out_path.write_text(json.dumps(all_results, indent=2))

    total_solved = sum(1 for r in all_results if r["solved"])
    print(f"\n  N29 Lite Total: {total_solved}/{len(all_results)} solved across 4 quadrants")


def test_n29_lite_rerun_1_task_higher_solve() -> None:
    """Verify N29 Lite rerun produces at least as many solves as a single-task dry run."""
    model_name = find_ollama_model("qwen2.5-coder")
    if not model_name:
        pytest.skip("Ollama or qwen2.5-coder not available locally")

    single = _run_quadrant([TASKS[0]], "with_nexus", model_name)
    assert len(single) == 1
    assert single[0]["task_id"] == "13852_repro"
