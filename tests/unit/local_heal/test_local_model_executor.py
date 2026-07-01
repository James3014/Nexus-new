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
def make_test_request(
    task_id: str,
    problem_statement: str = "test",
    repo_root: str = "/workspace",
    target_file: str = "file.py",
    selected_capabilities: tuple[str, ...] = ("local_model_executor",),
    evidence_refs: tuple[str, ...] = (),
    dry_run: bool = False,
    execution_topology: str = "single_local_model",
    route_context: dict | None = None,
) -> LocalModelExecutorRequest:
    if route_context is None:
        route_context = {
            "signal_snapshot": {
                "execution_topology": execution_topology,
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit"
            }
        }
    else:
        route_context = dict(route_context)
        if "signal_snapshot" in route_context and isinstance(route_context["signal_snapshot"], dict):
            snap = dict(route_context["signal_snapshot"])
            snap.setdefault("execution_topology", execution_topology)
            snap.setdefault("model_call_allowed", True)
            snap.setdefault("selected_executor", "local_model")
            snap.setdefault("executor_model", "qwen2.5-coder:7b")
            snap.setdefault("protocol_mode", "anchored_edit")
            route_context["signal_snapshot"] = snap
    return LocalModelExecutorRequest(
        task_id=task_id,
        problem_statement=problem_statement,
        repo_root=repo_root,
        target_file=target_file,
        selected_capabilities=selected_capabilities,
        evidence_refs=evidence_refs,
        dry_run=dry_run,
        route_context=route_context,
    )



def test_dry_run_does_not_call_provider():
    called = False

    def mock_gen(req: LocalModelProviderRequest) -> str:
        nonlocal called
        called = True
        return "mock patch"

    provider = InjectedLocalModelProvider(mock_gen)
    req = make_test_request(
        task_id="test-1",
        problem_statement="dry run test",
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
    req = make_test_request(
        task_id="test-2",
        problem_statement="unavailable test",
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
    req = make_test_request(
        task_id="test-3",
        problem_statement="authority test",
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
    req = make_test_request(
        task_id="test-4",
        problem_statement="hash test",
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
    req = make_test_request(
        task_id="test-anchored",
        problem_statement="fix hello",
        route_context={
            "locked_search": "print('hello')",
            "target_symbol": "print",
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "protocol_mode": "anchored_edit"
            }
        },
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
    req = make_test_request(
        task_id="test-diff",
        problem_statement="fix hello",
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "protocol_mode": "unified_diff"
            }
        }
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    assert "unified diff" in captured_prompt.lower()
    assert resp.raw_model_metadata.get("protocol_mode") == "unified_diff"


def test_topology_single_local_model_preserves_behavior() -> None:
    def mock_gen(req: LocalModelProviderRequest) -> str:
        return "some patch"

    provider = InjectedLocalModelProvider(mock_gen)
    req = make_test_request(
        task_id="test-top-single",
        problem_statement="topology test",
    )
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("execution_topology") == "single_local_model"


def test_topology_local_committee_via_signal_snapshot(monkeypatch) -> None:
    """Env var is NOT used for topology — signal_snapshot in route_context is the source."""
    
    def mock_gen(req: LocalModelProviderRequest) -> str:
        return "some patch"

    provider = InjectedLocalModelProvider(mock_gen)
    req = make_test_request(
        task_id="test-top-committee",
        problem_statement="topology test",
        evidence_refs=("ref-dummy",),
        route_context={
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "local_committee_enabled": True,
                "proposer_specs": [{"model": "qwen2.5-coder:7b", "role": "primary"}],
                "judge_model": "qwen2.5:3b"
            }
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
    req = make_test_request(
        task_id="test-single-topo",
        problem_statement="test",
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

    req = make_test_request(
        task_id="test-task",
        problem_statement="test",
        evidence_refs=("ref1",),
        route_context={
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "proposer_specs": [{"model": "qwen2.5-coder:7b", "role": "primary"}],
                "judge_model": "qwen2.5:3b"
            }
        }
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
    def mock_select_candidate(candidates, selected_capabilities=(), ctx=None):
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

    req = make_test_request(
        task_id="test-task",
        problem_statement="test",
        evidence_refs=("ref1",),
        route_context={
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "proposer_specs": [{"model": "qwen2.5-coder:7b", "role": "primary"}],
                "judge_model": "qwen2.5:3b"
            }
        }
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
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit"
            },
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
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit"
            },
        },
    )
    assert _resolve_execution_topology(req) == "local_committee_only"


def test_resolve_topology_route_context_top_level_fallback():
    """route_context top-level execution_topology fails closed (raises ValueError) when no signal_snapshot."""
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
    with pytest.raises(ValueError, match="Missing signal_snapshot in route_context"):
        _resolve_execution_topology(req)


def test_resolve_topology_request_field_fallback():
    """request.execution_topology fails closed (raises ValueError) when route_context has no topology."""
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
    with pytest.raises(ValueError, match="Missing signal_snapshot in route_context"):
        _resolve_execution_topology(req)


def test_resolve_topology_no_topology_defaults_to_single():
    """No topology anywhere fails closed (raises ValueError)."""
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
    with pytest.raises(ValueError, match="Missing signal_snapshot in route_context"):
        _resolve_execution_topology(req)


def test_resolve_topology_env_var_not_used():
    """Missing signal_snapshot raises ValueError even with env vars present."""
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
        with pytest.raises(ValueError, match="Missing signal_snapshot in route_context"):
            _resolve_execution_topology(req)
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

    req = make_test_request(
        task_id="test-signal-snapshot",
        problem_statement="test",
        evidence_refs=("ref1",),
        route_context={
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "proposer_specs": [{"model": "qwen2.5-coder:7b", "role": "primary"}],
                "judge_model": "qwen2.5:3b"
            }
        }
    )
    provider = InjectedLocalModelProvider(lambda req: "patch")
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.raw_model_metadata.get("execution_topology") == "local_committee_only"
    assert provider_called is True


def test_local_assist_receipt_sections_attach_to_existing_local_model_executor_receipt() -> None:
    req = make_test_request(
        task_id="test-telemetry-attach",
        problem_statement="test",
        evidence_refs=("ref1",),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "model_call_allowed": True,
            }
        }
    )
    provider = InjectedLocalModelProvider(lambda req: "patch")
    resp = LocalModelExecutor.run(req, provider=provider)
    telemetry = resp.raw_model_metadata.get("local_assist_telemetry")
    assert telemetry is not None
    assert isinstance(telemetry, dict)
    assert "compaction" in telemetry
    assert "memory_rerank" in telemetry
    assert "preflight" in telemetry
    assert "cheap_judge" in telemetry
    assert "isolation" in telemetry
    assert "verifier" in telemetry
    assert "learning_closure" in telemetry


def test_local_assist_receipt_sections_do_not_create_new_capability_names() -> None:
    from nexus.services.local_heal.local_assist_receipts import LocalAssistTelemetryCollection
    telemetry = LocalAssistTelemetryCollection()
    d = telemetry.to_dict()
    assert "name" not in d
    assert "capability" not in d
    assert "route_mode" not in d
    assert "authority" not in d


def test_receipt_wiring_does_not_change_gate_passed() -> None:
    req = make_test_request(
        task_id="test-telemetry-gate",
        problem_statement="test",
        evidence_refs=("ref1",),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "model_call_allowed": True,
            }
        }
    )
    provider = InjectedLocalModelProvider(lambda req: "patch")
    resp = LocalModelExecutor.run(req, provider=provider)
    telemetry = resp.raw_model_metadata.get("local_assist_telemetry")
    assert telemetry is not None
    assert resp.raw_model_metadata.get("gate_passed") is not True


def test_receipt_wiring_does_not_change_solved_outcome() -> None:
    req = make_test_request(
        task_id="test-telemetry-solved",
        problem_statement="test",
        evidence_refs=("ref1",),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "protocol_mode": "anchored_edit",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "model_call_allowed": True,
            }
        }
    )
    provider = InjectedLocalModelProvider(lambda req: "patch")
    resp = LocalModelExecutor.run(req, provider=provider)
    telemetry = resp.raw_model_metadata.get("local_assist_telemetry")
    assert telemetry is not None
    assert resp.raw_model_metadata.get("solved") is not True


def test_receipt_wiring_missing_sections_safe() -> None:
    from nexus.services.local_heal.local_assist_receipts import build_local_assist_telemetry_from_executor_meta
    telemetry = build_local_assist_telemetry_from_executor_meta({})
    d = telemetry.to_dict()
    assert d["compaction"] is None
    assert d["memory_rerank"] is None
    assert d["preflight"] is None
    assert d["cheap_judge"] is None
    assert d["isolation"] is None
    assert d["verifier"] is None
    assert d["learning_closure"] is None


# ---------------------------------------------------------------------------
# C6: Provider Timeout Telemetry Tests
# ---------------------------------------------------------------------------

def test_c6_timeout_sec_forwarded_from_signal_snapshot() -> None:
    """provider_timeout_sec in signal_snapshot must be forwarded to LocalModelProviderRequest."""
    captured: list[LocalModelProviderRequest] = []

    def capture_fn(req: LocalModelProviderRequest) -> str:
        captured.append(req)
        return "patch content"

    req = make_test_request(
        "c6-timeout-forward",
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "executor_provider": "ollama",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "provider_timeout_sec": 90,
            }
        }
    )
    provider = InjectedLocalModelProvider(capture_fn)
    LocalModelExecutor.run(req, provider=provider)
    assert len(captured) == 1
    assert captured[0].timeout_sec == 90.0, (
        f"Expected timeout_sec=90.0, got {captured[0].timeout_sec}"
    )


def test_c6_default_timeout_sec_is_120() -> None:
    """When provider_timeout_sec is absent, default must be 120.0 (not 30.0)."""
    captured: list[LocalModelProviderRequest] = []

    def capture_fn(req: LocalModelProviderRequest) -> str:
        captured.append(req)
        return ""

    req = make_test_request(
        "c6-default-timeout",
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "executor_provider": "ollama",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                # provider_timeout_sec intentionally absent
            }
        }
    )
    provider = InjectedLocalModelProvider(capture_fn)
    LocalModelExecutor.run(req, provider=provider)
    assert len(captured) == 1
    assert captured[0].timeout_sec == 120.0, (
        f"Expected default timeout_sec=120.0, got {captured[0].timeout_sec}"
    )


def test_c6_timeout_does_not_produce_solved() -> None:
    """A provider that times out (model_called=False) must never produce solved=True."""
    from nexus.services.local_heal.local_model_provider import (
        LocalModelProviderResponse,
        LocalModelProvider as _LMP,
    )

    class TimeoutProvider(_LMP):
        def generate(self, request):
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name=request.model_name,
                output_text="",
                error="ollama_timeout: timed out after 30.0s (limit=30.0s)",
                timed_out=True,
                requested_timeout_sec=request.timeout_sec,
                elapsed_sec=30.1,
                effective_timeout_sec=request.timeout_sec,
            )

    req = make_test_request("c6-no-solve-on-timeout")
    resp = LocalModelExecutor.run(req, provider=TimeoutProvider())
    assert not resp.local_model_called
    assert resp.timeout is True
    assert resp.candidate_patch == ""
    meta = resp.raw_model_metadata
    assert meta.get("solved") is not True


def test_c6_timed_out_true_when_provider_sets_timed_out() -> None:
    """LocalModelExecutorResponse.timeout must be True when provider.timed_out=True."""
    from nexus.services.local_heal.local_model_provider import LocalModelProviderResponse, LocalModelProvider as _LMP

    class AlwaysTimeoutProvider(_LMP):
        def generate(self, request):
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name="test-model",
                output_text="",
                error="ollama_timeout: timed out after 120.0s (limit=120.0s)",
                timed_out=True,
                requested_timeout_sec=120.0,
                elapsed_sec=120.1,
                effective_timeout_sec=120.0,
            )

    req = make_test_request("c6-timeout-flag")
    resp = LocalModelExecutor.run(req, provider=AlwaysTimeoutProvider())
    assert resp.timeout is True
    assert resp.local_model_called is False
    assert resp.error != ""


def test_c6_output_with_no_error_not_classified_as_timeout() -> None:
    """A provider that returns output_len>0 with empty error must NOT be classified as timeout."""
    req = make_test_request("c6-real-output")
    provider = InjectedLocalModelProvider(lambda _: "<<<<<<< REPLACE\nfixed\n>>>>>>> REPLACE\n")
    resp = LocalModelExecutor.run(req, provider=provider)
    assert resp.local_model_called is True
    assert resp.timeout is False
    assert resp.error == ""

