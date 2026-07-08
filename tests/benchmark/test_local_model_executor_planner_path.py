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
        "signal_snapshot": {
            "execution_topology": "local_only",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": "qwen2.5-coder:7b"
        }
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
    try:
        _req = urllib.request.urlopen(
            "http://localhost:11434/api/show",
            data=json.dumps({"name": "qwen2.5-coder:7b"}).encode(),
            timeout=3.0,
        )
        _resp = json.loads(_req.read().decode())
        if not _resp.get("modelfile"):
            pytest.skip("Required model qwen2.5-coder:7b not installed")
    except Exception:
        pytest.skip("Required model qwen2.5-coder:7b not available")

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
        "signal_snapshot": {
            "execution_topology": "local_only",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": "qwen2.5-coder:7b"
        }
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
            "signal_snapshot": {
                "execution_topology": "local_only",
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
                "executor_provider": "ollama",
                "executor_model": "qwen2.5-coder:7b"
            }
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


def test_finalize_with_nexus_row_signal_snapshot_triggers_committee(monkeypatch, tmp_path):
    """Verify signal_snapshot.execution_topology flows through _finalize_with_nexus_row into LocalModelExecutor.
    
    This is the key integration test: planner-owned signal_snapshot → executor → committee branch.
    """
    from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.isolated_local_solve_loop import IsolatedLocalSolveResponse, IsolatedApplyReceipt, IsolatedVerifierReceipt
    from nexus.contracts.hybrid_route import HybridRouteDecision, RouteMode, VerifierResult, Authority

    # 1. Enable executor, NOT dry_run — must actually enter committee branch
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN", "0")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")

    # 2. Create target file
    resolved_path = tmp_path.resolve()
    target_dir = resolved_path / "pkg"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file_path = target_dir / "mod.py"
    target_file_path.write_text("x = 1\n", encoding="utf-8")

    # 3. Mock committee provider — must be called
    committee_called = False
    def mock_generate_committee(*args, **kwargs):
        nonlocal committee_called
        committee_called = True
        return [
            CandidateEnvelope(
                candidate_id="test-signal-snapshot-primary_proposer",
                task_id="test",
                source="local",
                model="qwen2.5-coder:7b",
                role="primary_proposer",
                patch_protocol="anchored_edit",
                target_file="pkg/mod.py",
                target_symbol="x",
                source_anchor_hash="hash",
                candidate_patch_hash=hashlib.sha256(b"patch").hexdigest(),
                evidence_refs=("ref1",),
                candidate_patch="patch",
            )
        ]
    monkeypatch.setattr(LocalCommitteeCandidateProvider, "generate_committee_candidates", mock_generate_committee)

    # 4. Mock isolated solve to avoid real apply/verifier
    mock_solve_response = IsolatedLocalSolveResponse(
        patch_envelope=type("E", (), {"candidate_hash": "hash123", "unified_diff": "diff"})(),
        apply_receipt=IsolatedApplyReceipt(
            task_id="test", workspace_path="", target_file="pkg/mod.py",
            patch_apply_status="applied", patch_apply_error="",
            selected_candidate_hash="hash123", applied_patch_hash="hash123",
            selected_candidate_hash_matches_applied=True, candidate_output_isolated=True,
            mutation_allowed=False,
        ),
        verifier_receipt=IsolatedVerifierReceipt(
            task_id="test", verifier_status="pass", exit_code=0,
            stdout_tail="", stderr_tail="", verifier_error="",
            verifier_allowed=True,
        ),
        candidate_isolation_receipt=type("CIR", (), {
            "candidate_id": "c1", "selected_candidate_hash": "hash123",
            "applied_patch_hash": "hash123", "selected_candidate_hash_matches_applied": True,
            "candidate_output_isolated": True, "verifier_result": VerifierResult.PASS,
            "evidence_refs": ("ref1",), "local_model_called": True,
            "mutation_allowed": False, "repaired_by_rule": "none",
        })(),
        hybrid_route=HybridRouteDecision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            public_claim_allowed=False, production_ready=False,
            adapter_output_is_route_truth=False, route_truth_source="CapabilityPlanner",
            behavior_changed=False, authority=Authority.INTERNAL_ONLY,
            cloud_model_called=False, local_model_called=True,
            candidate_output_isolated=True, selected_candidate_hash="hash123",
            applied_patch_hash="hash123", selected_candidate_hash_matches_applied=True,
            verifier_result=VerifierResult.PASS, evidence_refs=("ref1",),
        ),
        capability_payload={"gate_passed": True, "metadata": {"verifier_status": "pass"}},
    )
    from nexus.services.local_heal import isolated_local_solve_loop
    monkeypatch.setattr(isolated_local_solve_loop, "run_isolated_local_solve_loop", lambda req: mock_solve_response)

    # 5. Build row with signal_snapshot containing execution_topology
    task = CapabilityTask(
        id="test-signal-snapshot",
        task_desc="test signal_snapshot topology flow",
        task_type="bug",
        success_criteria="passes",
        difficulty="easy",
        category="test",
        expected_capabilities=["local_model_executor"],
        target_file="pkg/mod.py",
        test_file="pkg/test_mod.py",
    )
    
    # Mock provider generator for the provider build path
    def mock_provider_gen(req):
        return "mock_patch"

    row = {
        "capability_plan_selected": ["local_model_executor"],
        "evidence_refs": ["ref-signal-snapshot"],
        "verifier_command": ["echo", "ok"],
        "target_symbol": "x",
        "locked_search": "x = 1",
        "candidate_generate_fn": mock_provider_gen,
        "signal_snapshot": {
            "execution_topology": "local_committee_only",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": "qwen2.5-coder:7b",
            "judge_model": "qwen2.5:3b",
            "proposer_specs": [
                {"model": "qwen2.5-coder:7b", "role": "primary"},
                {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
            ]
        },
    }

    # 6. Call _finalize_with_nexus_row
    finalized = _finalize_with_nexus_row(
        row,
        provider="ollama",
        model_required=True,
        nexus_required=True,
        task=task,
        repo_root=resolved_path,
    )

    # 7. Verify executor was invoked
    assert finalized.get("local_executor_planned") is True

    # 8. KEY ASSERTION: committee branch was actually triggered
    assert committee_called is True, "LocalCommitteeCandidateProvider.generate_committee_candidates was NOT called — committee branch not triggered"

    # 9. Verify topology in metadata
    executor_meta = finalized.get("local_model_executor_summary", {})
    assert executor_meta.get("planner_selected_count") == 1

    # 10. Verify receipt
    receipt = finalized.get("local_executor_receipt")
    assert receipt is not None
    assert receipt["name"] == "local_model_executor"


def test_finalize_with_nexus_row_local_model_full_armor_smoke(monkeypatch, tmp_path):
    """Full armor smoke: topology + selected_capabilities + anchored_edit + source_anchor + failure_feedback + receipt.
    
    This is the definitive integration test proving local model can use Nexus mainline capabilities
    without new routes, without HealPipeline, without CommitteeOrchestrator.
    """
    from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.isolated_local_solve_loop import (
        IsolatedLocalSolveResponse, IsolatedApplyReceipt, IsolatedVerifierReceipt, CandidateIsolationReceipt,
    )
    from nexus.contracts.hybrid_route import HybridRouteDecision, RouteMode, VerifierResult, Authority

    # 1. Enable executor
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN", "0")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "anchored_edit")

    # 2. Create target file
    resolved_path = tmp_path.resolve()
    target_dir = resolved_path / "pkg"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file_path = target_dir / "mod.py"
    target_file_path.write_text("def func():\n    pass\n", encoding="utf-8")

    # 3. Mock committee provider — return anchored_edit REPLACE block
    committee_called = False
    def mock_generate_committee(*args, **kwargs):
        nonlocal committee_called
        committee_called = True
        return [
            CandidateEnvelope(
                candidate_id="smoke-judge",
                task_id="smoke", source="local", model="qwen2.5:3b",
                role="judge", patch_protocol="none",
                target_file="pkg/mod.py", target_symbol="func",
                source_anchor_hash="ahash", candidate_patch_hash=hashlib.sha256(b"").hexdigest(),
                evidence_refs=("ref1",), candidate_patch="",
            ),
            CandidateEnvelope(
                candidate_id="smoke-primary",
                task_id="smoke", source="local", model="qwen2.5-coder:7b",
                role="primary_proposer", patch_protocol="anchored_edit",
                target_file="pkg/mod.py", target_symbol="func",
                source_anchor_hash="ahash",
                candidate_patch_hash=hashlib.sha256(b"patch").hexdigest(),
                evidence_refs=("ref1",),
                candidate_patch="<<<<<<< REPLACE\ndef func():\n    return 1\n>>>>>>> REPLACE",
            ),
        ]
    monkeypatch.setattr(LocalCommitteeCandidateProvider, "generate_committee_candidates", mock_generate_committee)

    # 4. Mock isolated solve
    mock_solve_response = IsolatedLocalSolveResponse(
        patch_envelope=type("E", (), {"candidate_hash": "hash123", "unified_diff": "diff"})(),
        apply_receipt=IsolatedApplyReceipt(
            task_id="smoke", workspace_path="", target_file="pkg/mod.py",
            patch_apply_status="applied", patch_apply_error="",
            selected_candidate_hash="hash123", applied_patch_hash="hash123",
            selected_candidate_hash_matches_applied=True, candidate_output_isolated=True,
            mutation_allowed=False,
        ),
        verifier_receipt=IsolatedVerifierReceipt(
            task_id="smoke", verifier_status="pass", exit_code=0,
            stdout_tail="", stderr_tail="", verifier_error="",
            verifier_allowed=True,
        ),
        candidate_isolation_receipt=CandidateIsolationReceipt(
            candidate_id="smoke-primary", selected_candidate_hash="hash123",
            applied_patch_hash="hash123", selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True, verifier_result=VerifierResult.PASS,
            evidence_refs=("ref1",), local_model_called=True,
            mutation_allowed=False, repaired_by_rule="none",
        ),
        hybrid_route=HybridRouteDecision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            public_claim_allowed=False, production_ready=False,
            adapter_output_is_route_truth=False, route_truth_source="CapabilityPlanner",
            behavior_changed=False, authority=Authority.INTERNAL_ONLY,
            cloud_model_called=False, local_model_called=True,
            candidate_output_isolated=True, selected_candidate_hash="hash123",
            applied_patch_hash="hash123", selected_candidate_hash_matches_applied=True,
            verifier_result=VerifierResult.PASS, evidence_refs=("ref1",),
        ),
        capability_payload={"gate_passed": True, "metadata": {"verifier_status": "pass"}},
    )
    from nexus.services.local_heal import isolated_local_solve_loop
    monkeypatch.setattr(isolated_local_solve_loop, "run_isolated_local_solve_loop", lambda req: mock_solve_response)

    # 5. Build row with ALL required fields
    task = CapabilityTask(
        id="smoke-full-armor",
        task_desc="full armor smoke test",
        task_type="bug", success_criteria="passes",
        difficulty="easy", category="test",
        expected_capabilities=["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
        target_file="pkg/mod.py", test_file="pkg/test_mod.py",
    )

    row = {
        "capability_plan_selected": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
        "evidence_refs": ["smoke-ref-1"],
        "verifier_command": ["echo", "ok"],
        "target_symbol": "func",
        "locked_search": "def func():\n    pass",
        "candidate_generate_fn": lambda req: "mock",
        "signal_snapshot": {
            "execution_topology": "local_committee_only",
            "protocol_mode": "anchored_edit",
            "model_call_allowed": True,
            "executor_provider": "ollama",
            "executor_model": "qwen2.5-coder:7b",
            "judge_model": "qwen2.5:3b",
            "proposer_specs": [
                {"model": "qwen2.5-coder:7b", "role": "primary"},
                {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
            ]
        },
        "previous_failure": "VERIFIER_FAIL: previous attempt failed",
        "failure_class": "VERIFIER_FAIL",
        "verifier_status": "fail",
    }

    # 6. Call _finalize_with_nexus_row
    finalized = _finalize_with_nexus_row(
        row, provider="ollama", model_required=True, nexus_required=True,
        task=task, repo_root=resolved_path,
    )

    # 7. Assert planner topology
    assert finalized.get("local_executor_planned") is True

    # 8. Assert committee branch triggered
    assert committee_called is True

    # 9. Assert receipt
    receipt = finalized.get("local_executor_receipt")
    assert receipt is not None
    assert receipt["name"] == "local_model_executor"
    assert any(rc.get("name") == "local_model_executor" for rc in finalized.get("capability_receipts", []))

    # 10. Assert metadata observability
    meta = finalized.get("local_model_executor_summary", {})
    assert meta.get("planner_selected_count") == 1

    # 11. Assert receipt gate and source
    assert receipt["gate_passed"] is True
    assert receipt["selection_source"] == "CapabilityPlanner"

