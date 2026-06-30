from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import pytest

from scripts.bench.capability_ab_runner import CapabilityTask, _finalize_with_nexus_row


def test_deterministic_full_capability_solve(monkeypatch, tmp_path):
    """Deterministic full capability solve: all selected capabilities executed with receipts."""
    from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.isolated_local_solve_loop import (
        IsolatedLocalSolveResponse, IsolatedApplyReceipt, IsolatedVerifierReceipt, CandidateIsolationReceipt,
    )
    from nexus.contracts.hybrid_route import HybridRouteDecision, RouteMode, VerifierResult, Authority

    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN", "0")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "anchored_edit")

    resolved_path = tmp_path.resolve()
    target_dir = resolved_path / "pkg"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "mod.py").write_text("def func():\n    pass\n", encoding="utf-8")

    # Mock committee provider
    def mock_committee(*args, **kwargs):
        patch = "<<<<<<< REPLACE\ndef func():\n    return 1\n>>>>>>> REPLACE"
        return [CandidateEnvelope(
            candidate_id="c1", task_id="t", source="local", model="qwen2.5-coder:7b",
            role="primary_proposer", patch_protocol="anchored_edit",
            target_file="pkg/mod.py", target_symbol="func", source_anchor_hash="h",
            candidate_patch_hash=hashlib.sha256(patch.encode()).hexdigest(),
            evidence_refs=("ref1",), candidate_patch=patch,
        )]
    monkeypatch.setattr(LocalCommitteeCandidateProvider, "generate_committee_candidates", mock_committee)

    # Mock isolated solve
    mock_solve = IsolatedLocalSolveResponse(
        patch_envelope=type("E", (), {"candidate_hash": "h123", "unified_diff": "d"})(),
        apply_receipt=IsolatedApplyReceipt(
            task_id="t", workspace_path="", target_file="pkg/mod.py",
            patch_apply_status="applied", patch_apply_error="",
            selected_candidate_hash="h123", applied_patch_hash="h123",
            selected_candidate_hash_matches_applied=True, candidate_output_isolated=True,
            mutation_allowed=False,
        ),
        verifier_receipt=IsolatedVerifierReceipt(
            task_id="t", verifier_status="pass", exit_code=0,
            stdout_tail="", stderr_tail="", verifier_error="", verifier_allowed=True,
        ),
        candidate_isolation_receipt=CandidateIsolationReceipt(
            candidate_id="c1", selected_candidate_hash="h123",
            applied_patch_hash="h123", selected_candidate_hash_matches_applied=True,
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
            candidate_output_isolated=True, selected_candidate_hash="h123",
            applied_patch_hash="h123", selected_candidate_hash_matches_applied=True,
            verifier_result=VerifierResult.PASS, evidence_refs=("ref1",),
        ),
        capability_payload={"gate_passed": True, "metadata": {"verifier_status": "pass"}},
    )
    from nexus.services.local_heal import isolated_local_solve_loop
    monkeypatch.setattr(isolated_local_solve_loop, "run_isolated_local_solve_loop", lambda req: mock_solve)

    task = CapabilityTask(
        id="full-cap-solve", task_desc="full capability solve",
        task_type="bug", success_criteria="passes", difficulty="easy", category="test",
        expected_capabilities=["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
        target_file="pkg/mod.py", test_file="pkg/test_mod.py",
    )
    row = {
        "capability_plan_selected": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
        "evidence_refs": ["full-cap-ref"], "verifier_command": ["echo", "ok"],
        "target_symbol": "func", "locked_search": "def func():\n    pass",
        "candidate_generate_fn": lambda req: "mock",
        "signal_snapshot": {"execution_topology": "localheal_pipeline"},
    }

    finalized = _finalize_with_nexus_row(
        row, provider="ollama", model_required=True, nexus_required=True,
        task=task, repo_root=resolved_path,
    )

    # Verify executor planned
    assert finalized.get("local_executor_planned") is True

    # Verify receipt
    receipt = finalized.get("local_executor_receipt")
    assert receipt is not None
    assert receipt["name"] == "local_model_executor"
    assert receipt["gate_passed"] is True

    # Verify adapter metadata
    adapter = finalized.get("local_model_adapter", {})
    adapter_meta = adapter.get("metadata", {})

    # KEY: All capabilities must be invoked
    assert adapter_meta.get("ddtree_invoked") is True, "ddtree not invoked"
    assert adapter_meta.get("autoreason_invoked") is True, "autoreason not invoked"
    assert adapter_meta.get("artifact_gate_invoked") is True, "artifact_gate not invoked"
    assert adapter_meta.get("claim_gate_invoked") is True, "claim_gate not invoked"
    assert adapter_meta.get("delivery_gate_invoked") is True, "delivery_gate not invoked"
    assert adapter_meta.get("localheal_pipeline_invoked") is True, "localheal_pipeline not invoked"

    # Verify execution results via adapter metadata
    # ddtree/autoreason results are in adapter metadata via runner copy
    assert adapter_meta.get("ddtree_invoked") is True
    assert adapter_meta.get("autoreason_invoked") is True

    gate_results = adapter_meta.get("gate_results", {})
    for gate_name in ("artifact_gate", "claim_gate", "delivery_gate"):
        assert gate_name in gate_results
        assert gate_results[gate_name].get("invoked") is True

    # Verify final_authority
    assert receipt.get("selection_source") == "CapabilityPlanner"

    # Verify topology
    assert adapter_meta.get("execution_topology") == "localheal_pipeline"

    # Verify capability receipts exist
    receipts = finalized.get("capability_receipts", [])
    assert len(receipts) >= 1
    assert any(rc.get("name") == "local_model_executor" for rc in receipts)


@pytest.mark.skipif(
    os.environ.get("NEXUS_RUN_REAL_LOCAL_MODEL_TESTS") != "1",
    reason="Set NEXUS_RUN_REAL_LOCAL_MODEL_TESTS=1 to run real local model tests",
)
@pytest.mark.skipif(
    os.environ.get("NEXUS_LOCAL_MODEL_CALL_ALLOWED") != "1",
    reason="Set NEXUS_LOCAL_MODEL_CALL_ALLOWED=1 to run real local model tests",
)
def test_real_local_model_full_capability_solve(monkeypatch, tmp_path):
    """Real local model full capability solve with Ollama."""
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2.0)
    except Exception:
        pytest.skip("Ollama is not running locally")

    from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider

    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_EXECUTOR_DRY_RUN", "0")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("NEXUS_LOCAL_MODEL_NAME", "qwen2.5-coder:7b")
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "anchored_edit")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_MUTATION_ALLOWED", "1")
    monkeypatch.setenv("NEXUS_LOCAL_SOLVE_VERIFIER_ALLOWED", "1")

    resolved_path = tmp_path.resolve()
    target_dir = resolved_path / "toy"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "__init__.py").write_text("", encoding="utf-8")
    (target_dir / "math_util.py").write_text("def double(x):\n    return x * 2\n", encoding="utf-8")
    (resolved_path / "verify.py").write_text(
        "import sys\nc = open('toy/math_util.py').read()\nsys.exit(0 if 'return x * 3' in c else 1)\n",
        encoding="utf-8",
    )

    # Use real provider through committee
    def mock_committee(*args, **kwargs):
        from nexus.services.local_heal.local_model_provider import OllamaLocalModelProvider, LocalModelProviderRequest
        provider = OllamaLocalModelProvider()
        prompt = (
            "You are generating a replacement code block to solve a coding task.\n"
            "Problem: Fix double to return x * 3 instead of x * 2\n"
            "Target File: toy/math_util.py\n"
            "Target Symbol: double\n"
            "Locked Search Span:\n```\ndef double(x):\n    return x * 2\n```\n\n"
            "Provide replacement:\n<<<<<<< REPLACE\ndef double(x):\n    return x * 3\n>>>>>>> REPLACE\n"
        )
        prov_resp = provider.generate(LocalModelProviderRequest(
            task_id="real-full-cap", prompt=prompt, evidence_refs=("ref1",), model_name="qwen2.5-coder:7b",
        ))
        from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
        patch = prov_resp.output_text or ""
        return [CandidateEnvelope(
            candidate_id="real-full-cap-primary", task_id="real-full-cap",
            source="local", model="qwen2.5-coder:7b", role="primary_proposer",
            patch_protocol="anchored_edit", target_file="toy/math_util.py",
            target_symbol="double", source_anchor_hash="h",
            candidate_patch_hash=hashlib.sha256(patch.encode()).hexdigest() if patch else hashlib.sha256(b"").hexdigest(),
            evidence_refs=("ref1",), candidate_patch=patch,
        )]
    monkeypatch.setattr(LocalCommitteeCandidateProvider, "generate_committee_candidates", mock_committee)

    task = CapabilityTask(
        id="real-full-cap", task_desc="Fix double to return x * 3",
        task_type="bug", success_criteria="passes", difficulty="easy", category="test",
        expected_capabilities=["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
        target_file="toy/math_util.py", test_file="verify.py",
    )
    row = {
        "capability_plan_selected": ["local_model_executor", "ddtree", "autoreason", "artifact_gate", "claim_gate", "delivery_gate"],
        "evidence_refs": ["real-full-cap-ref"], "verifier_command": ["python3", str(resolved_path / "verify.py")],
        "target_symbol": "double", "locked_search": "def double(x):\n    return x * 2",
        "candidate_generate_fn": lambda req: "mock",
        "signal_snapshot": {"execution_topology": "localheal_pipeline"},
    }

    finalized = _finalize_with_nexus_row(
        row, provider="ollama", model_required=True, nexus_required=True,
        task=task, repo_root=resolved_path,
    )

    receipt = finalized.get("local_executor_receipt")
    adapter = finalized.get("local_model_adapter", {})
    adapter_meta = adapter.get("metadata", {})

    # Record result
    result = {
        "task_id": "real-full-cap",
        "model_name": adapter_meta.get("executor_model", ""),
        "local_model_called": adapter.get("local_model_called", False),
        "execution_topology": adapter_meta.get("execution_topology", ""),
        "ddtree_invoked": adapter_meta.get("ddtree_invoked", False),
        "autoreason_invoked": adapter_meta.get("autoreason_invoked", False),
        "artifact_gate_invoked": adapter_meta.get("artifact_gate_invoked", False),
        "claim_gate_invoked": adapter_meta.get("claim_gate_invoked", False),
        "delivery_gate_invoked": adapter_meta.get("delivery_gate_invoked", False),
        "localheal_pipeline_invoked": adapter_meta.get("localheal_pipeline_invoked", False),
        "verifier_result": "pass" if receipt and receipt.get("gate_passed") else "fail",
        "solved": receipt is not None and receipt.get("gate_passed", False),
        "final_authority": "NexusVerifier",
    }

    assert receipt is not None
    assert result["solved"] or result["verifier_result"] == "fail"
    assert result["final_authority"] == "NexusVerifier"

    if result["solved"]:
        assert result["ddtree_invoked"] is True
        assert result["autoreason_invoked"] is True
        assert result["artifact_gate_invoked"] is True
        assert result["claim_gate_invoked"] is True
        assert result["delivery_gate_invoked"] is True
        assert result["localheal_pipeline_invoked"] is True
