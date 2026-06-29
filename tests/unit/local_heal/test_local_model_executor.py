from __future__ import annotations

import hashlib
import pytest

from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
    _resolve_execution_topology,
)
from nexus.services.local_heal.local_model_provider import (
    InertLocalModelProvider,
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
)


def test_dry_run_does_not_call_provider():
    called = False

    def mock_gen(req: LocalModelProviderRequest) -> str:
        nonlocal called
        called = True
        return "mock patch"

    provider = InjectedLocalModelProvider(mock_gen)
    req = LocalModelExecutorRequest(
        task_id="test-1",
        problem_statement="dry run test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=True,
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.invoked is False
    assert resp.local_model_called is False
    assert resp.candidate_patch == ""
    assert resp.candidate_hash == hashlib.sha256(b"").hexdigest()
    assert called is False


def test_provider_unavailable_returns_blocked_response():
    provider = InertLocalModelProvider()
    req = LocalModelExecutorRequest(
        task_id="test-2",
        problem_statement="unavailable test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.invoked is True
    assert resp.local_model_called is False
    assert resp.error == "provider_unavailable"
    assert resp.candidate_patch == ""


def test_response_has_no_public_prod_authority():
    def mock_gen(req: LocalModelProviderRequest) -> str:
        return "mock diff"

    provider = InjectedLocalModelProvider(mock_gen)
    req = LocalModelExecutorRequest(
        task_id="test-3",
        problem_statement="authority test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    # Check that public_claim or production_ready is NOT in any fields
    d = resp.__dict__
    assert "public_claim_allowed" not in d
    assert "production_ready" not in d
    assert "behavior_changed" not in d


def test_candidate_hash_deterministic():
    patch = "+++ b/file.py\n--- a/file.py\n@@ -1,1 +1,2 @@\n-old\n+new"
    expected_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest()

    def mock_gen(req: LocalModelProviderRequest) -> str:
        return patch

    provider = InjectedLocalModelProvider(mock_gen)
    req = LocalModelExecutorRequest(
        task_id="test-4",
        problem_statement="hash test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.candidate_patch == patch
    assert resp.candidate_hash == expected_hash


def test_local_model_executor_uses_anchored_edit_prompt_when_protocol_mode_enabled(monkeypatch):
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "anchored_edit")
    captured_prompt = ""

    def mock_gen(req: LocalModelProviderRequest) -> str:
        nonlocal captured_prompt
        captured_prompt = req.prompt
        return "<<<<<<< REPLACE\nprint('world')\n>>>>>>> REPLACE"

    provider = InjectedLocalModelProvider(mock_gen)
    req = LocalModelExecutorRequest(
        task_id="test-anchored",
        problem_statement="fix hello",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
        route_context={"locked_search": "print('hello')", "target_symbol": "print"},
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    assert "REPLACE" in captured_prompt
    assert "Locked Search Span" in captured_prompt
    assert "print('hello')" in captured_prompt
    assert "unified diff" not in captured_prompt.lower()
    assert resp.raw_model_metadata.get("protocol_mode") == "anchored_edit"


def test_local_model_executor_unified_diff_prompt_only_when_compat_mode(monkeypatch):
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "unified_diff")
    captured_prompt = ""

    def mock_gen(req: LocalModelProviderRequest) -> str:
        nonlocal captured_prompt
        captured_prompt = req.prompt
        return "diff patch"

    provider = InjectedLocalModelProvider(mock_gen)
    req = LocalModelExecutorRequest(
        task_id="test-diff",
        problem_statement="fix hello",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    assert "unified diff" in captured_prompt.lower()
    assert resp.raw_model_metadata.get("protocol_mode") == "unified_diff"


def test_topology_single_local_model_preserves_behavior() -> None:
    def mock_gen(req: LocalModelProviderRequest) -> str:
        return "some patch"

    provider = InjectedLocalModelProvider(mock_gen)
    req = LocalModelExecutorRequest(
        task_id="test-top-single",
        problem_statement="topology test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
        execution_topology="single_local_model",
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("execution_topology") == "single_local_model"


def test_topology_local_committee_via_signal_snapshot(monkeypatch) -> None:
    """Env var is NOT used for topology — signal_snapshot in route_context is the source."""
    
    def mock_gen(req: LocalModelProviderRequest) -> str:
        return "some patch"

    provider = InjectedLocalModelProvider(mock_gen)
    req = LocalModelExecutorRequest(
        task_id="test-top-committee",
        problem_statement="topology test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=("ref-dummy",),
        dry_run=False,
        route_context={
            "signal_snapshot": {"execution_topology": "local_committee_only"},
        },
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("execution_topology") == "local_committee_only"


def test_local_model_executor_single_topology_uses_single_provider_path(monkeypatch):
    called_count = 0
    def mock_gen(req: LocalModelProviderRequest) -> str:
        nonlocal called_count
        called_count += 1
        return "single patch"

    provider = InjectedLocalModelProvider(mock_gen)
    req = LocalModelExecutorRequest(
        task_id="test-single-topo",
        problem_statement="test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=(),
        dry_run=False,
        execution_topology="single_local_model",
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("execution_topology") == "single_local_model"
    assert called_count == 1


def test_local_model_executor_committee_topology_uses_committee_provider(monkeypatch):
    from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    import hashlib

    provider_called = False
    def mock_generate_committee_candidates(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return [
            CandidateEnvelope(
                candidate_id="test-task-primary_proposer-success",
                task_id="test-task",
                source="local",
                model="qwen2.5-coder:7b",
                role="primary_proposer",
                patch_protocol="anchored_edit",
                target_file="file.py",
                target_symbol="func",
                source_anchor_hash="hash",
                candidate_patch_hash=hashlib.sha256(b"patch").hexdigest(),
                evidence_refs=("ref1",),
                candidate_patch="<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
            )
        ]

    monkeypatch.setattr(LocalCommitteeCandidateProvider, "generate_committee_candidates", mock_generate_committee_candidates)

    req = LocalModelExecutorRequest(
        task_id="test-task",
        problem_statement="test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=("ref1",),
        dry_run=False,
        execution_topology="local_committee_only",
    )
    
    provider = InjectedLocalModelProvider(lambda req: "patch")
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("execution_topology") == "local_committee_only"
    assert provider_called is True
    assert resp.candidate_patch != ""


def test_local_model_executor_committee_topology_uses_candidate_decision_adapter(monkeypatch):
    from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
    from nexus.services.local_heal.candidate_decision_adapter import CandidateDecisionAdapter, CandidateDecisionResponse
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    import hashlib

    dummy_patch = "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"
    dummy_envelope = CandidateEnvelope(
        candidate_id="c-1",
        task_id="test-task",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=hashlib.sha256(dummy_patch.encode()).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=dummy_patch,
    )
    monkeypatch.setattr(LocalCommitteeCandidateProvider, "generate_committee_candidates", lambda *a, **k: [dummy_envelope])

    adapter_called = False
    def mock_select_candidate(candidates, selected_capabilities=()):
        nonlocal adapter_called
        adapter_called = True
        return CandidateDecisionResponse(
            selected_candidate_id="c-1",
            selected_candidate_patch="<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
            ranking_trace=["ranked"],
            selected_by="custom_logic",
            decision_evidence_refs=("ref1",),
        )
    monkeypatch.setattr(CandidateDecisionAdapter, "select_candidate", mock_select_candidate)

    req = LocalModelExecutorRequest(
        task_id="test-task",
        problem_statement="test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=("ref1",),
        dry_run=False,
        execution_topology="local_committee_only",
    )
    provider = InjectedLocalModelProvider(lambda req: "patch")
    resp = LocalModelExecutor.run(req, provider=provider)
    assert adapter_called is True
    assert resp.candidate_patch != ""
    assert resp.raw_model_metadata.get("selected_by") == "custom_logic"


def test_local_model_executor_committee_judge_never_outputs_patch():
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    import hashlib
    with pytest.raises(ValueError) as excinfo:
        CandidateEnvelope(
            candidate_id="judge-1",
            task_id="test-task",
            source="local",
            model="qwen2.5:3b",
            role="judge",
            patch_protocol="none",
            target_file="file.py",
            target_symbol="func",
            source_anchor_hash="hash",
            candidate_patch_hash=hashlib.sha256(b"").hexdigest(),
            evidence_refs=("ref1",),
            candidate_patch="some_patch_violating_rules",
        )
    assert "cannot generate repair patches" in str(excinfo.value)


def test_finalize_with_nexus_row_still_has_single_executor_seam(monkeypatch):
    import ast
    from pathlib import Path

    runner_path = Path("/Users/jameschen/Workspace/nexus/scripts/bench/capability_ab_runner.py")
    if not runner_path.exists():
        pytest.skip("capability_ab_runner.py not found in workspace")

    tree = ast.parse(runner_path.read_text(encoding="utf-8"))
    
    finalize_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_finalize_with_nexus_row":
            finalize_func = node
            break
            
    assert finalize_func is not None, "Could not find _finalize_with_nexus_row function in runner file"
    
    for node in ast.walk(finalize_func):
        if isinstance(node, ast.Import):
            for name in node.names:
                assert "HealPipeline" not in name.name
                assert "CommitteeOrchestrator" not in name.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "HealPipeline" not in node.module
                assert "CommitteeOrchestrator" not in node.module
            for name in node.names:
                assert "HealPipeline" not in name.name
                assert "CommitteeOrchestrator" not in name.name


def test_resolve_topology_signal_snapshot_takes_priority():
    """signal_snapshot.execution_topology is first priority."""
    req = LocalModelExecutorRequest(
        task_id="t1",
        problem_statement="test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
        execution_topology="single_local_model",
        route_context={
            "signal_snapshot": {"execution_topology": "local_committee_only"},
            "execution_topology": "single_local_model",
        },
    )
    assert _resolve_execution_topology(req) == "local_committee_only"


def test_resolve_topology_signal_snapshot_over_request_field():
    """signal_snapshot beats request.execution_topology."""
    req = LocalModelExecutorRequest(
        task_id="t2",
        problem_statement="test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
        execution_topology="single_local_model",
        route_context={
            "signal_snapshot": {"execution_topology": "local_committee_only"},
        },
    )
    assert _resolve_execution_topology(req) == "local_committee_only"


def test_resolve_topology_route_context_top_level_fallback():
    """route_context top-level execution_topology is fallback when no signal_snapshot."""
    req = LocalModelExecutorRequest(
        task_id="t3",
        problem_statement="test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
        execution_topology="single_local_model",
        route_context={
            "execution_topology": "local_committee_only",
        },
    )
    assert _resolve_execution_topology(req) == "local_committee_only"


def test_resolve_topology_request_field_fallback():
    """request.execution_topology is fallback when route_context has no topology."""
    req = LocalModelExecutorRequest(
        task_id="t4",
        problem_statement="test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
        execution_topology="local_committee_only",
        route_context={},
    )
    assert _resolve_execution_topology(req) == "local_committee_only"


def test_resolve_topology_no_topology_defaults_to_single():
    """No topology anywhere defaults to single_local_model."""
    req = LocalModelExecutorRequest(
        task_id="t5",
        problem_statement="test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
        execution_topology="",
        route_context={},
    )
    assert _resolve_execution_topology(req) == "single_local_model"


def test_resolve_topology_env_var_not_used():
    """NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY env is NOT used by _resolve_execution_topology."""
    import os
    os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"] = "local_committee_only"
    try:
        req = LocalModelExecutorRequest(
            task_id="t6",
            problem_statement="test",
            repo_root="/workspace",
            target_file="file.py",
            selected_capabilities=(),
            evidence_refs=(),
            execution_topology="",
            route_context={},
        )
        result = _resolve_execution_topology(req)
        # Env var should NOT be the source — falls back to default
        assert result == "single_local_model"
    finally:
        del os.environ["NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY"]


def test_executor_run_uses_planner_topology_from_signal_snapshot(monkeypatch):
    """Executor.run() uses topology from signal_snapshot in route_context."""
    from nexus.services.local_heal.local_committee_candidate_provider import LocalCommitteeCandidateProvider
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    import hashlib

    provider_called = False
    def mock_generate_committee_candidates(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return [
            CandidateEnvelope(
                candidate_id="test-signal-snapshot-primary_proposer",
                task_id="test",
                source="local",
                model="qwen2.5-coder:7b",
                role="primary_proposer",
                patch_protocol="anchored_edit",
                target_file="file.py",
                target_symbol="func",
                source_anchor_hash="hash",
                candidate_patch_hash=hashlib.sha256(b"patch").hexdigest(),
                evidence_refs=("ref1",),
                candidate_patch="patch",
            )
        ]

    monkeypatch.setattr(LocalCommitteeCandidateProvider, "generate_committee_candidates", mock_generate_committee_candidates)

    req = LocalModelExecutorRequest(
        task_id="test-signal-snapshot",
        problem_statement="test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=("ref1",),
        dry_run=False,
        execution_topology="single_local_model",
        route_context={
            "signal_snapshot": {"execution_topology": "local_committee_only"},
        },
    )
    provider = InjectedLocalModelProvider(lambda req: "patch")
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("execution_topology") == "local_committee_only"
    assert provider_called is True

