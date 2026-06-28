from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

# 自帶 Path 載入
repo_root = str(Path(__file__).resolve().parents[2])
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
)
from nexus.engine.capability_receipt_adapters import LocalHealReceiptAdapter


FIXTURES = [
    {
        "task_id": "t_batch_1",
        "description": "single-line arithmetic bug",
        "source_code": "def compute(x):\n    return x * 2 + 5\n",
        "problem_statement": "Correct the formula in compute: multiply x by 3 instead of 2.",
        "target_symbol": "compute",
        "locked_search": "return x * 2 + 5",
        "verifier_command": ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.compute(2) == 11"],
    },
    {
        "task_id": "t_batch_2",
        "description": "off-by-one bug",
        "source_code": "def get_range(n):\n    return list(range(1, n))\n",
        "problem_statement": "Fix off-by-one bug in get_range. It should return numbers from 1 up to n inclusive.",
        "target_symbol": "get_range",
        "locked_search": "return list(range(1, n))",
        "verifier_command": ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.get_range(3) == [1, 2, 3]"],
    },
    {
        "task_id": "t_batch_3",
        "description": "wrong comparison operator",
        "source_code": "def is_positive(x):\n    return x < 0\n",
        "problem_statement": "Fix wrong comparison operator in is_positive. It should return True for values greater than 0.",
        "target_symbol": "is_positive",
        "locked_search": "return x < 0",
        "verifier_command": ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.is_positive(5) is True"],
    },
    {
        "task_id": "t_batch_4",
        "description": "wrong return variable",
        "source_code": "def square_and_cube(x):\n    sq = x ** 2\n    cu = x ** 3\n    return sq\n",
        "problem_statement": "Fix the wrong return variable. square_and_cube should return the cube variable (cu) instead of sq.",
        "target_symbol": "square_and_cube",
        "locked_search": "return sq",
        "verifier_command": ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.square_and_cube(2) == 8"],
    },
    {
        "task_id": "t_batch_5",
        "description": "wrong function call argument",
        "source_code": "def helper(a, b):\n    return a - b\ndef process(x):\n    return helper(x, 10)\n",
        "problem_statement": "Fix the wrong argument passed to helper in process. The second argument should be 5 instead of 10.",
        "target_symbol": "process",
        "locked_search": "return helper(x, 10)",
        "verifier_command": ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.process(15) == 10"],
    },
    {
        "task_id": "t_batch_6",
        "description": "missing base case",
        "source_code": "def fib(n):\n    if n == 1:\n        return 1\n    return fib(n-1) + fib(n-2)\n",
        "problem_statement": "Fix recursive function fib by handling the missing base case for n == 0 or negative values, return n if n <= 1.",
        "target_symbol": "fib",
        "locked_search": "if n == 1:\n        return 1",
        "verifier_command": ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.fib(0) == 0"],
    },
    {
        "task_id": "t_batch_7",
        "description": "boolean inversion",
        "source_code": "def check_admin(user):\n    is_admin = False\n    return not is_admin\n",
        "problem_statement": "Fix boolean inversion. check_admin should return is_admin directly, without negation.",
        "target_symbol": "check_admin",
        "locked_search": "return not is_admin",
        "verifier_command": ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.check_admin(None) is False"],
    },
    {
        "task_id": "t_batch_8",
        "description": "string literal mismatch",
        "source_code": "def greet(name):\n    return f\"Hi {name}\"\n",
        "problem_statement": "Fix the greeting prefix. It should return 'Hello {name}' instead of 'Hi {name}'.",
        "target_symbol": "greet",
        "locked_search": "return f\"Hi {name}\"",
        "verifier_command": ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.greet('Bob') == 'Hello Bob'"],
    },
    {
        "task_id": "t_batch_9",
        "description": "list indexing bug",
        "source_code": "def get_last(lst):\n    return lst[len(lst)]\n",
        "problem_statement": "Fix list indexing bug. get_last should return the last element of lst using valid index lst[-1].",
        "target_symbol": "get_last",
        "locked_search": "return lst[len(lst)]",
        "verifier_command": ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.get_last([1, 2, 9]) == 9"],
    },
    {
        "task_id": "t_batch_10",
        "description": "simple exception handling bug",
        "source_code": "def safe_divide(a, b):\n    try:\n        return a / b\n    except ValueError:\n        return None\n",
        "problem_statement": "Fix exception handling block in safe_divide. It should catch ZeroDivisionError instead of ValueError when dividing by zero.",
        "target_symbol": "safe_divide",
        "locked_search": "except ValueError:",
        "verifier_command": ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.safe_divide(5, 0) is None"],
    },
]


def find_ollama_model(prefix: str) -> str | None:
    url = os.environ.get("NEXUS_OLLAMA_URL", "http://127.0.0.1:11434/api/tags").strip()
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for m in data.get("models", []):
                name = m.get("name", "")
                if name.startswith(prefix):
                    return name
            return None
    except Exception:
        return None


def run_batch_eval() -> dict[str, Any]:
    model_prefix = "qwen2.5-coder"
    full_model_name = find_ollama_model(model_prefix)
    if not full_model_name:
        print(f"Ollama or model {model_prefix} not available locally.")
        return {"status": "skipped", "reason": "model_not_available"}
        
    results_dir = Path(repo_root) / "artifacts" / "runtime" / "real_qwen_small_batch_eval_v0"
    results_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = results_dir / "results.jsonl"
    
    if jsonl_path.exists():
        jsonl_path.unlink()
        
    attempted = 0
    solved_count = 0
    blocked_count = 0
    env_updates = {
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE": "1",
        "NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED": "1",
        "NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_NAME": full_model_name,
    }
    
    for fixture in FIXTURES:
        task_id = fixture["task_id"]
        attempted += 1
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
            }
            
            request = LocalHealCapabilityRequest(
                task_id=task_id,
                problem_statement=fixture["problem_statement"],
                evidence_refs=("batch-eval-ref",),
                executor_controls=controls,
            )
            
            from unittest.mock import patch
            with patch.dict(os.environ, env_updates):
                response = LocalHealCapabilityAdapter.run(request)
            
            receipt_adapter = LocalHealReceiptAdapter()
            receipt = receipt_adapter.build(claim_verified=True, payload=response.capability_payload)
            
            duration = time.time() - start_time
            
            metadata = response.capability_payload.get("metadata", {})
            route_mode = response.hybrid_route.route_mode.value
            gate_passed = receipt.gate_passed
            verifier_status = metadata.get("verifier_status", "blocked")
            sel_hash = metadata.get("selected_candidate_hash", "")
            app_hash = metadata.get("applied_patch_hash", "")
            pub_claim = response.hybrid_route.public_claim_allowed
            prod_ready = response.hybrid_route.production_ready
            
            is_solved = (
                route_mode == "local_only_executed"
                and gate_passed is True
                and verifier_status == "pass"
                and bool(sel_hash)
                and bool(app_hash)
                and pub_claim is False
                and prod_ready is False
            )
            
            if is_solved:
                solved_count += 1
            else:
                blocked_count += 1
                
            result_item = {
                "task_id": task_id,
                "model_name": full_model_name,
                "model_called": response.hybrid_route.local_model_called,
                "selected_candidate_hash_present": bool(sel_hash),
                "route_mode": route_mode,
                "gate_passed": gate_passed,
                "verifier_status": verifier_status,
                "solved": is_solved,
                "fallback_block_reason": response.hybrid_route.fallback_block_reason,
                "normalizer_used": metadata.get("normalized", False),
                "normalization_reason": metadata.get("normalization_reason", ""),
                "repair_attempted": metadata.get("repair_attempted", False),
                "repair_success": metadata.get("repair_success", False),
                "repaired_by_rule": metadata.get("repaired_by_rule", "none"),
                "still_within_locked_span": metadata.get("still_within_locked_span", False),
                "attempt_count": metadata.get("attempt_count", 1),
                "retry_attempted": metadata.get("retry_attempted", False),
                "retry_reason": metadata.get("retry_reason", "none"),
                "retry_success": metadata.get("retry_success", False),
                "final_failure_class": metadata.get("final_failure_class", "none"),
                "public_claim_allowed": pub_claim,
                "production_ready": prod_ready,
                "duration_sec": round(duration, 2),
            }
            
            with open(jsonl_path, "a", encoding="utf-8") as f_out:
                f_out.write(json.dumps(result_item) + "\n")
                
            workspace_path = response.hybrid_route.metadata.get("workspace_path", "")
            if workspace_path and os.path.exists(workspace_path):
                try:
                    shutil.rmtree(workspace_path)
                except Exception:
                    pass
                    
    return {
        "status": "completed",
        "attempted_count": attempted,
        "solved_count": solved_count,
        "blocked_count": blocked_count,
        "solve_rate": round(solved_count / attempted, 2) if attempted else 0.0,
    }


if __name__ == "__main__":
    res = run_batch_eval()
    print(json.dumps(res, indent=2))
