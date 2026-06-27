from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.request
import urllib.error
from unittest import mock
import pytest

from scripts.local_heal.run_controlled_local_solve_fixture import main


def find_ollama_model(prefix: str) -> str | None:
    """Return the full model name (with tag) matching the given prefix, or None."""
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


def test_real_ollama_solve_lane_factorial_fix() -> None:
    model_prefix = "qwen2.5-coder"
    full_model_name = find_ollama_model(model_prefix)
    if full_model_name is None:
        pytest.skip(f"Ollama service or model matching '{model_prefix}' is not available locally, skipping real model solve lane")
        
    with tempfile.TemporaryDirectory() as src_root:
        test_file = "f.py"
        src_path = os.path.join(src_root, test_file)
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("def factorial(n):\n    if n == 0:\n        return 1\n    return n * factorial(n - 2)\n")
            
        with tempfile.TemporaryDirectory() as temp_dir:
            output_json = os.path.join(temp_dir, "output.json")
            
            verifier_cmd = ["python3", "-c", "import sys; sys.path.append('.'); import f; assert f.factorial(3) == 6"]
            
            env_overrides = {
                "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
                "NEXUS_LOCAL_MODEL_NAME": full_model_name,
            }
            
            argv = [
                "run_controlled_local_solve_fixture.py",
                "--task-id", "t_real_ollama_fac",
                "--source-root", src_root,
                "--target-file", test_file,
                "--target-symbol", "factorial",
                "--locked-search", "return n * factorial(n - 2)",
                "--problem-statement", "Fix the recursive call step in factorial. Change n - 2 to n - 1 so that factorial works correctly.",
                "--verifier-command-json", json.dumps(verifier_cmd),
                "--provider-mode", "ollama",
                "--output-json", output_json,
            ]
            
            with mock.patch.dict(os.environ, env_overrides):
                with mock.patch("sys.argv", argv):
                    exit_code = main()
                    
            assert exit_code == 0
            with open(output_json, "r", encoding="utf-8") as f:
                res = json.load(f)
                
            print("REAL QWEN OUTPUT:", res)
            assert res["public_claim_allowed"] is False
            assert res["production_ready"] is False
            assert res["invoked"] is True
            
            block_reason = res.get("fallback_block_reason", "")
            assert "local_model_not_called" not in block_reason, (
                f"Model {full_model_name} was available but not called. block_reason={block_reason}"
            )
            
            if res["route_mode"] == "local_only_executed":
                assert res["gate_passed"] is True
                assert res["metadata"].get("verifier_status") == "pass"
            elif res["route_mode"] == "local_only_blocked":
                content_blockers = {
                    "HASH_MISMATCH", "SEARCH_MISMATCH", "VERIFIER_FAIL",
                    "missing_unified_diff", "constraint_violation",
                    "patch_outside_locked_span", "target_file_mismatch",
                }
                known_acceptable = {
                    "hash_match_not_proven", "missing_applied_patch_hash",
                    "missing_candidate_isolation", "missing_selected_candidate_hash",
                    "mutation_not_allowed", "verifier_fail_or_not_run",
                }
                actual_blockers = set(block_reason.split(";")) if block_reason else set()
                infra_blockers = actual_blockers - content_blockers - known_acceptable - {""}
                print(f"Model produced output but blocked (content/parse issues). blockers={actual_blockers}")
                assert not infra_blockers, (
                    f"Unexpected infrastructure blockers detected (model should have been called and pipeline should be intact): {infra_blockers}"
                )
            else:
                pytest.fail(f"Unexpected route mode: {res['route_mode']}")
