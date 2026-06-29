from __future__ import annotations

import hashlib
import os
from pathlib import Path
import pytest

from scripts.bench.capability_ab_runner import (
    CapabilityTask,
    _finalize_with_nexus_row,
)
from nexus.services.local_heal.local_model_provider import LocalModelProviderRequest


def test_local_model_executor_planner_path(monkeypatch, tmp_path):
    # Ensure controlled test classification
    # Label: Controlled Test, not real Qwen proof
    
    # 1. Enable local model executor environment gate
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN", "0") # Trigger active execution
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED", "1")
    
    # 2. Define mock candidate generator & create source file to patch
    resolved_path = tmp_path.resolve()
    target_dir = resolved_path / "sympy/functions/special"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file_path = target_dir / "zeta_functions.py"
    target_file_path.write_text("if a is S.One:\n", encoding="utf-8")

    patch_content = (
        "--- a/sympy/functions/special/zeta_functions.py\n"
        "+++ b/sympy/functions/special/zeta_functions.py\n"
        "@@ -1 +1 @@\n"
        "-if a is S.One:\n"
        "+if a == S.One:\n"
    )
    expected_hash = hashlib.sha256(patch_content.encode("utf-8")).hexdigest()
    
    called = False
    def mock_generate(req: LocalModelProviderRequest) -> str:
        nonlocal called
        called = True
        print("DEBUG_MOCK_GENERATE_TRIGGERED with hash:", expected_hash)
        return patch_content

    # 3. Build mocked task and row context
    task = CapabilityTask(
        id="sympy__sympy-13852",
        task_desc="Fix zeta function evaluation logic",
        task_type="bug",
        success_criteria="pytest passes",
        difficulty="medium",
        category="math",
        expected_capabilities=["local_model_executor", "artifact_gate", "claim_gate", "delivery_gate"],
        target_file="sympy/functions/special/zeta_functions.py",
        test_file="sympy/functions/special/tests/test_zeta_functions.py",
    )
    
    row = {
        "capability_plan_selected": ["local_model_executor", "artifact_gate", "claim_gate", "delivery_gate"],
        "evidence_refs": ["test-evidence-ref"],
        "candidate_generate_fn": mock_generate,
        "verifier_command": ["echo", "mock_verifier_pass"],
        "target_symbol": "eval",
        "locked_search": "if a is S.One:",
    }
    
    # 4. Invoke finalize seam (mainline收斂點)
    finalized = _finalize_with_nexus_row(
        row,
        provider="ollama",
        model_required=True,
        nexus_required=True,
        task=task,
        repo_root=resolved_path,
    )
    
    # 5. Assertions - Verification against N1 Requirements
    assert called is True
    assert finalized.get("local_executor_planned") is True
    assert finalized.get("local_executor_selected_by") == "CapabilityPlanner"
    assert finalized.get("local_model_called") is True
    assert finalized.get("candidate_hash") == expected_hash
    
    # Verify summary fields
    summary = finalized.get("local_model_executor_summary")
    assert summary is not None
    assert summary["planner_selected_count"] == 1
    assert summary["executor_invoked_count"] == 1
    assert summary["local_model_called_count"] == 1
    assert summary["candidate_hash_count"] == 1
    assert summary["capability_receipt_attached_count"] == 1
    assert summary["artifact_gate_count"] == 0
    assert summary["claim_gate_count"] == 0
    assert summary["delivery_gate_count"] == 0
    
    # Invariants check
    assert summary["public_claim_allowed_count"] == 0
    assert summary["production_ready_count"] == 0
    assert summary["behavior_changed_count"] == 0
    assert summary["route_truth_violation_count"] == 0
    
    # Verify capability receipts integration
    receipts = finalized.get("capability_receipts", [])
    assert any(rc.get("name") == "local_model_executor" for rc in receipts)
    
    # Verify receipt fields
    receipt = finalized.get("local_executor_receipt")
    assert receipt is not None
    assert receipt["name"] == "local_model_executor"
    print("DEBUG_RECEIPT_FAILURE_REASON:", receipt.get("failure_reason"))
    assert receipt["gate_passed"] is True # Since verifier passed in mock
    assert receipt["outcome_contributed"] is False
    assert receipt["selection_source"] == "CapabilityPlanner"
    assert receipt["executor_id"] == "local_model:qwen2.5-coder:7b"


def test_local_model_executor_real_provider_smoke(monkeypatch, tmp_path):
    # Only run if explicitly requested or Ollama is online
    import urllib.request
    import json
    
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
    except Exception:
        pytest.skip("Ollama is not running locally")

    # 1. Enable local model executor environment gate
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN", "0") 
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED", "1")
    
    # Create target file with zeta function code
    resolved_path = tmp_path.resolve()
    target_dir = resolved_path / "sympy/functions/special"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file_path = target_dir / "zeta_functions.py"
    target_file_path.write_text("class zeta:\n    def eval(self):\n        if a is S.One:\n            pass\n", encoding="utf-8")

    task = CapabilityTask(
        id="sympy__sympy-13852",
        task_desc="Fix zeta function evaluation logic by replacing 'a is S.One' with 'a == S.One'. Return ONLY a unified diff patching sympy/functions/special/zeta_functions.py.",
        task_type="bug",
        success_criteria="pytest passes",
        difficulty="medium",
        category="math",
        expected_capabilities=["local_model_executor", "artifact_gate", "claim_gate", "delivery_gate"],
        target_file="sympy/functions/special/zeta_functions.py",
        test_file="sympy/functions/special/tests/test_zeta_functions.py",
    )
    
    row = {
        "capability_plan_selected": ["local_model_executor", "artifact_gate", "claim_gate", "delivery_gate"],
        "evidence_refs": ["real-ollama-smoke-evidence"],
        "verifier_command": ["echo", "mock_verifier_pass"],
        "target_symbol": "eval",
        "locked_search": "if a is S.One:",
    }
    
    # 4. Invoke finalize seam
    finalized = _finalize_with_nexus_row(
        row,
        provider="ollama",
        model_required=True,
        nexus_required=True,
        task=task,
        repo_root=resolved_path,
    )
    
    # 5. Assertions
    assert finalized.get("local_executor_planned") is True
    assert finalized.get("local_executor_selected_by") == "CapabilityPlanner"
    
    # Ollama call check
    assert finalized.get("local_model_called") is True
    assert finalized.get("candidate_hash") != ""
    
    # Summary check
    summary = finalized.get("local_model_executor_summary")
    assert summary is not None
    assert summary["local_model_called_count"] == 1
    assert summary["public_claim_allowed_count"] == 0
    assert summary["production_ready_count"] == 0
    
    # Receipt check
    receipt = finalized.get("local_executor_receipt")
    assert receipt is not None
    assert receipt["name"] == "local_model_executor"
    assert receipt["executor_id"] == "local_model:qwen2.5-coder:7b"


@pytest.mark.skip(reason="Skip concurrency real solve by default")
def test_local_model_executor_concurrency_real_solve(monkeypatch):
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
    except Exception:
        pytest.skip("Ollama is not running locally")

    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN", "0")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE", "1")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_ISOLATED_ENABLE", "1")
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "anchored_edit")
    
    repo_root = Path(__file__).resolve().parents[2]
    target_file = "nexus/verifiers/domain/concurrency/buggy_targets_batch_b02.py"
    target_file_path = repo_root / target_file
    
    backup_content = target_file_path.read_text(encoding="utf-8")
    
    try:
        task = CapabilityTask(
            id="concurrency_bug_02",
            task_desc=(
                "Fix the thread-safety race condition in BuggyIdempotentExecutor inside nexus/verifiers/domain/concurrency/buggy_targets_batch_b02.py.\n"
                "Here is the COMPLETE code of nexus/verifiers/domain/concurrency/buggy_targets_batch_b02.py:\n\n"
                f"{backup_content}\n\n"
                "Use the threading.Lock already initialized as self._lock in __init__ to protect the execute() method.\n"
                "Return ONLY a standard unified diff patching nexus/verifiers/domain/concurrency/buggy_targets_batch_b02.py. No prose, no explanations, only the unified diff wrapped in a ```diff fenced block."
            ),
            task_type="bug",
            success_criteria="pytest passes",
            difficulty="medium",
            category="concurrency",
            expected_capabilities=["local_model_executor", "artifact_gate", "claim_gate", "delivery_gate"],
            target_file=target_file,
            test_file="tests/unit/verifiers/concurrency/test_race.py",
        )
        
        row = {
            "capability_plan_selected": ["local_model_executor", "artifact_gate", "claim_gate", "delivery_gate"],
            "evidence_refs": ["real-concurrency-solve-evidence"],
            "verifier_command": ["uv", "run", "pytest", "tests/unit/verifiers/concurrency/test_race.py"],
            "target_symbol": "BuggyIdempotentExecutor",
            "locked_search": (
                "class BuggyIdempotentExecutor:\n"
                "    \"\"\"模擬重試冪等性失效 (Double Execution)\"\"\"\n"
                "    def __init__(self):\n"
                "        self.executed = False\n"
                "        self.call_count = 0\n"
                "        self._lock = threading.Lock()\n"
                "\n"
                "    def execute(self):\n"
                "        if not self.executed:\n"
                "            time.sleep(0.01) # Race window\n"
                "            self.call_count += 1\n"
                "            self.executed = True"
            ),
        }
        
        finalized = _finalize_with_nexus_row(
            row,
            provider="ollama",
            model_required=True,
            nexus_required=True,
            task=task,
            repo_root=repo_root,
        )
        
        receipt = finalized.get("local_executor_receipt")
        assert receipt is not None
        assert receipt["gate_passed"] is True, f"Solve failed: {receipt.get('failure_reason')}"
        
    finally:
        target_file_path.write_text(backup_content, encoding="utf-8")

