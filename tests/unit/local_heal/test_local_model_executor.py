from __future__ import annotations

import hashlib
import pytest
from pathlib import Path

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
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
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
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
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
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b"
            }
        }
    )
    provider = InjectedLocalModelProvider(lambda req: "patch")
    resp = LocalModelExecutor.run(req, provider=provider)
    assert adapter_called is True
    assert resp.candidate_patch != ""
    assert resp.raw_model_metadata.get("selected_by") == "custom_logic"


def test_local_model_executor_committee_selected_patch_enters_isolation(monkeypatch):
    from unittest.mock import patch

    from nexus.services.local_heal.candidate_decision_adapter import (
        CandidateDecisionAdapter,
        CandidateDecisionResponse,
    )
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.local_committee_candidate_provider import (
        LocalCommitteeCandidateProvider,
    )

    diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"
    diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

    envelope = CandidateEnvelope(
        candidate_id="c-1",
        task_id="committee-isolation",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="unified_diff",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=diff_hash,
        evidence_refs=("ref1",),
        candidate_patch=diff_text,
    )
    monkeypatch.setattr(
        LocalCommitteeCandidateProvider,
        "generate_committee_candidates",
        lambda *a, **k: [envelope],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-1",
            selected_candidate_patch=diff_text,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="committee-isolation",
        problem_statement="test",
        evidence_refs=("ref1",),
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="committee-isolation",
            workspace_path="/tmp/ws",
            target_file="file.py",
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=diff_hash,
            applied_patch_hash=diff_hash,
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="committee-isolation",
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("candidate_isolation_attempted") is True
    assert meta.get("candidate_isolated") is True
    assert meta.get("candidate_output_isolated") is True
    assert meta.get("selected_candidate_hash") == diff_hash
    assert meta.get("applied_patch_hash") == diff_hash
    assert meta.get("selected_candidate_hash_matches_applied") is True
    assert meta.get("isolated_verifier_status") == "pass"
    assert meta.get("verifier_result") == "pass"
    assert meta.get("route_mode") == "local_only_executed"
    assert meta.get("authority") == "internal_only"
    assert meta.get("solved") is True


def test_local_model_executor_committee_parse_failure_skips_isolation(monkeypatch):
    from nexus.services.local_heal.candidate_decision_adapter import (
        CandidateDecisionAdapter,
        CandidateDecisionResponse,
    )
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.local_committee_candidate_provider import (
        LocalCommitteeCandidateProvider,
    )

    fenced_patch = "```python\nplain prose, not a real patch\n```"
    envelope = CandidateEnvelope(
        candidate_id="c-parse-fail",
        task_id="committee-parse-fail",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=hashlib.sha256(fenced_patch.encode("utf-8")).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=fenced_patch,
    )
    monkeypatch.setattr(
        LocalCommitteeCandidateProvider,
        "generate_committee_candidates",
        lambda *a, **k: [envelope],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-parse-fail",
            selected_candidate_patch=fenced_patch,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="committee-parse-fail",
        problem_statement="test",
        evidence_refs=("ref1",),
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
    meta = resp.raw_model_metadata
    assert meta.get("protocol_parse_failed") is True
    assert meta.get("candidate_isolation_attempted") is False
    assert meta.get("candidate_isolated") is False
    assert meta.get("candidate_output_isolated") is False
    assert meta.get("selected_candidate_hash") == ""
    assert meta.get("verifier_result") == "not_run"
    assert meta.get("solved") is not True


def test_local_model_executor_committee_outer_fence_wrap_is_unwrapped_and_isolated(monkeypatch):
    from nexus.services.local_heal.candidate_decision_adapter import (
        CandidateDecisionAdapter,
        CandidateDecisionResponse,
    )
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.local_committee_candidate_provider import (
        LocalCommitteeCandidateProvider,
    )
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch

    fenced_patch = "```python\n<<<<<<< REPLACE\ndef func():\n    return 1\n>>>>>>> REPLACE\n```"
    envelope = CandidateEnvelope(
        candidate_id="c-fence-unwrap",
        task_id="committee-fence-unwrap",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=hashlib.sha256(fenced_patch.encode("utf-8")).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=fenced_patch,
    )
    monkeypatch.setattr(
        LocalCommitteeCandidateProvider,
        "generate_committee_candidates",
        lambda *a, **k: [envelope],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-fence-unwrap",
            selected_candidate_patch=fenced_patch,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="committee-fence-unwrap",
        problem_statement="test",
        target_file="file.py",
        evidence_refs=("ref1",),
        route_context={
            "locked_search": "def func():\n    pass",
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        def _check_apply(apply_req):
            assert "```" not in apply_req.unified_diff
            assert apply_req.unified_diff.startswith("--- a/file.py\n+++ b/file.py\n")
            assert "+    return 1\n" in apply_req.unified_diff
            return IsolatedApplyReceipt(
                task_id="committee-fence-unwrap",
                workspace_path="/tmp/ws",
                target_file="file.py",
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash=apply_req.selected_candidate_hash,
                applied_patch_hash=apply_req.selected_candidate_hash,
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )

        mock_apply.side_effect = _check_apply
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="committee-fence-unwrap",
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("protocol_normalization", {}).get("outer_markdown_fence_unwrapped") is True
    assert meta.get("candidate_isolation_attempted") is True
    assert meta.get("candidate_isolated") is True
    assert meta.get("verifier_result") == "pass"


def test_local_model_executor_committee_replace_block_fence_is_unwrapped(monkeypatch):
    from nexus.services.local_heal.candidate_decision_adapter import (
        CandidateDecisionAdapter,
        CandidateDecisionResponse,
    )
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.local_committee_candidate_provider import (
        LocalCommitteeCandidateProvider,
    )
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch

    fenced_patch = (
        "<<<<<<< REPLACE\n"
        "```python\n"
        "def func():\n"
        "    return 1\n"
        "```\n"
        ">>>>>>> REPLACE\n"
    )
    envelope = CandidateEnvelope(
        candidate_id="c-replace-fence-unwrap",
        task_id="committee-replace-fence-unwrap",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=hashlib.sha256(fenced_patch.encode("utf-8")).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=fenced_patch,
    )
    monkeypatch.setattr(
        LocalCommitteeCandidateProvider,
        "generate_committee_candidates",
        lambda *a, **k: [envelope],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-replace-fence-unwrap",
            selected_candidate_patch=fenced_patch,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="committee-replace-fence-unwrap",
        problem_statement="test",
        target_file="file.py",
        evidence_refs=("ref1",),
        route_context={
            "locked_search": "def func():\n    pass",
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        def _check_apply(apply_req):
            assert "```" not in apply_req.unified_diff
            assert "+    return 1\n" in apply_req.unified_diff
            return IsolatedApplyReceipt(
                task_id="committee-replace-fence-unwrap",
                workspace_path="/tmp/ws",
                target_file="file.py",
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash=apply_req.selected_candidate_hash,
                applied_patch_hash=apply_req.selected_candidate_hash,
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )

        mock_apply.side_effect = _check_apply
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="committee-replace-fence-unwrap",
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("protocol_normalization", {}).get("replace_block_markdown_fence_unwrapped") is True
    assert meta.get("candidate_isolation_attempted") is True
    assert meta.get("candidate_isolated") is True


def test_local_model_executor_committee_raw_fenced_replacement_is_unwrapped(monkeypatch):
    from nexus.services.local_heal.candidate_decision_adapter import (
        CandidateDecisionAdapter,
        CandidateDecisionResponse,
    )
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.local_committee_candidate_provider import (
        LocalCommitteeCandidateProvider,
    )
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch

    fenced_patch = "```python\ndef func():\n    return 1\n```"
    envelope = CandidateEnvelope(
        candidate_id="c-raw-fence-unwrap",
        task_id="committee-raw-fence-unwrap",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=hashlib.sha256(fenced_patch.encode("utf-8")).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=fenced_patch,
    )
    monkeypatch.setattr(
        LocalCommitteeCandidateProvider,
        "generate_committee_candidates",
        lambda *a, **k: [envelope],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-raw-fence-unwrap",
            selected_candidate_patch=fenced_patch,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="committee-raw-fence-unwrap",
        problem_statement="test",
        target_file="file.py",
        evidence_refs=("ref1",),
        route_context={
            "locked_search": "def func():\n    pass",
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        def _check_apply(apply_req):
            assert "```" not in apply_req.unified_diff
            assert "+    return 1\n" in apply_req.unified_diff
            return IsolatedApplyReceipt(
                task_id="committee-raw-fence-unwrap",
                workspace_path="/tmp/ws",
                target_file="file.py",
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash=apply_req.selected_candidate_hash,
                applied_patch_hash=apply_req.selected_candidate_hash,
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )

        mock_apply.side_effect = _check_apply
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="committee-raw-fence-unwrap",
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("protocol_normalization", {}).get("outer_markdown_fence_unwrapped") is True
    assert meta.get("candidate_isolation_attempted") is True
    assert meta.get("candidate_isolated") is True


def test_local_model_executor_committee_prose_contamination_delegates_retry(monkeypatch):
    from nexus.services.local_heal.candidate_decision_adapter import (
        CandidateDecisionAdapter,
        CandidateDecisionResponse,
    )
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.local_committee_candidate_provider import (
        LocalCommitteeCandidateProvider,
    )
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch, MagicMock

    prose_patch = "```python\nHere is the fix:\ndef func():\n    return 1\n```"
    retried_diff = (
        "--- a/file.py\n"
        "+++ b/file.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def func():\n"
        "-    pass\n"
        "+def func():\n"
        "+    return 1\n"
    )
    envelope = CandidateEnvelope(
        candidate_id="c-prose-retry",
        task_id="committee-prose-retry",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=hashlib.sha256(prose_patch.encode("utf-8")).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=prose_patch,
    )
    monkeypatch.setattr(
        LocalCommitteeCandidateProvider,
        "generate_committee_candidates",
        lambda *a, **k: [envelope],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-prose-retry",
            selected_candidate_patch=prose_patch,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="committee-prose-retry",
        problem_statement="test",
        target_file="file.py",
        evidence_refs=("ref1",),
        route_context={
            "locked_search": "def func():\n    pass",
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        mock_pipeline_run.return_value = MagicMock(final_patch=retried_diff)
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="committee-prose-retry",
            workspace_path="/tmp/ws",
            target_file="file.py",
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=hashlib.sha256(retried_diff.encode("utf-8")).hexdigest(),
            applied_patch_hash=hashlib.sha256(retried_diff.encode("utf-8")).hexdigest(),
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="committee-prose-retry",
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("protocol_parse_error_kind") == "REPLACEMENT_PROSE_CONTAMINATION"
    assert meta.get("pipeline_retry_delegated") is True
    assert meta.get("candidate_isolation_attempted") is True
    assert meta.get("candidate_isolated") is True


def test_local_model_executor_committee_delegated_retry_records_second_attempt_metadata(monkeypatch):
    from nexus.services.local_heal.candidate_decision_adapter import (
        CandidateDecisionAdapter,
        CandidateDecisionResponse,
    )
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.local_committee_candidate_provider import (
        LocalCommitteeCandidateProvider,
    )
    from unittest.mock import patch, MagicMock

    prose_patch = "```python\nHere is the fix:\ndef func():\n    return 1\n```"
    retried_diff = "--- a/file.py\n+++ b/file.py\n@@ -1,2 +1,2 @@\n-def func():\n-    pass\n+def func():\n+    return 1\n"
    envelope = CandidateEnvelope(
        candidate_id="c-prose-retry-meta",
        task_id="committee-prose-retry-meta",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=hashlib.sha256(prose_patch.encode("utf-8")).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=prose_patch,
    )
    monkeypatch.setattr(
        LocalCommitteeCandidateProvider,
        "generate_committee_candidates",
        lambda *a, **k: [envelope],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-prose-retry-meta",
            selected_candidate_patch=prose_patch,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="committee-prose-retry-meta",
        problem_statement="test",
        target_file="file.py",
        evidence_refs=("ref1",),
        route_context={
            "locked_search": "def func():\n    pass",
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply"), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier"):
        mock_pipeline_run.return_value = MagicMock(
            final_patch=retried_diff,
            failure_reason="",
            model_decisions=[
                {
                    "phase": "patch",
                    "output_class": "VALID_SEARCH_REPLACE",
                    "parser_error_kind": "none",
                    "status": "SUCCESS",
                    "output_excerpt": "<<<<<<< REPLACE\n...",
                }
            ],
        )

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("pipeline_retry_delegated") is True
    assert meta.get("delegated_retry_final_patch_len") == len(retried_diff)
    assert meta.get("delegated_retry_output_class") == "VALID_SEARCH_REPLACE"
    assert meta.get("delegated_retry_parser_error_kind") == "none"
    assert meta.get("delegated_retry_status") == "SUCCESS"
    assert meta.get("delegated_retry_output_excerpt").startswith("<<<<<<< REPLACE")


def test_local_model_executor_committee_delegated_retry_records_failed_second_attempt_metadata(monkeypatch):
    from nexus.services.local_heal.candidate_decision_adapter import (
        CandidateDecisionAdapter,
        CandidateDecisionResponse,
    )
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.local_committee_candidate_provider import (
        LocalCommitteeCandidateProvider,
    )
    from unittest.mock import patch, MagicMock

    prose_patch = "```python\nHere is the fix:\ndef func():\n    return 1\n```"
    envelope = CandidateEnvelope(
        candidate_id="c-prose-retry-failed-meta",
        task_id="committee-prose-retry-failed-meta",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=hashlib.sha256(prose_patch.encode("utf-8")).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=prose_patch,
    )
    monkeypatch.setattr(
        LocalCommitteeCandidateProvider,
        "generate_committee_candidates",
        lambda *a, **k: [envelope],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-prose-retry-failed-meta",
            selected_candidate_patch=prose_patch,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="committee-prose-retry-failed-meta",
        problem_statement="test",
        target_file="file.py",
        evidence_refs=("ref1",),
        route_context={
            "locked_search": "def func():\n    pass",
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run:
        mock_pipeline_run.return_value = MagicMock(
            final_patch="",
            failure_reason="REPLACEMENT_PROSE_CONTAMINATION",
            model_decisions=[
                {
                    "phase": "patch",
                    "output_class": "NATURAL_LANGUAGE",
                    "parser_error_kind": "REPLACEMENT_PROSE_CONTAMINATION",
                    "status": "REPLACEMENT_PROSE_CONTAMINATION",
                    "output_excerpt": "Here is the fix:\n...",
                }
            ],
        )

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("pipeline_retry_delegated") is False
    assert meta.get("delegated_retry_failure_reason") == "REPLACEMENT_PROSE_CONTAMINATION"
    assert meta.get("delegated_retry_output_class") == "NATURAL_LANGUAGE"
    assert meta.get("delegated_retry_parser_error_kind") == "REPLACEMENT_PROSE_CONTAMINATION"
    assert meta.get("delegated_retry_status") == "REPLACEMENT_PROSE_CONTAMINATION"
    assert meta.get("delegated_retry_output_excerpt").startswith("Here is the fix:")


def test_local_model_executor_committee_delegated_retry_uses_reproduction_contract(monkeypatch):
    from nexus.services.local_heal.candidate_decision_adapter import (
        CandidateDecisionAdapter,
        CandidateDecisionResponse,
    )
    from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
    from nexus.services.local_heal.local_committee_candidate_provider import (
        LocalCommitteeCandidateProvider,
    )
    from unittest.mock import patch, MagicMock

    prose_patch = "```python\nHere is the fix:\ndef func():\n    return 1\n```"
    envelope = CandidateEnvelope(
        candidate_id="c-prose-retry-contract",
        task_id="committee-prose-retry-contract",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=hashlib.sha256(prose_patch.encode("utf-8")).hexdigest(),
        evidence_refs=("ref1",),
        candidate_patch=prose_patch,
    )
    monkeypatch.setattr(
        LocalCommitteeCandidateProvider,
        "generate_committee_candidates",
        lambda *a, **k: [envelope],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-prose-retry-contract",
            selected_candidate_patch=prose_patch,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="committee-prose-retry-contract",
        problem_statement="test",
        target_file="file.py",
        evidence_refs=("ref1",),
        route_context={
            "locked_search": "def func():\n    pass",
            "python_executable": "/tmp/task-venv/bin/python",
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    captured_ctx = None

    def _capture_run(ctx):
        nonlocal captured_ctx
        captured_ctx = ctx
        return MagicMock(final_patch="", failure_reason="SEARCH_MISMATCH", model_decisions=[])

    with patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run", side_effect=_capture_run), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply"), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier"):
        LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    assert captured_ctx is not None
    assert captured_ctx.problem_statement == "test"
    assert captured_ctx.attempt == 2
    assert captured_ctx.repro_script == ""
    assert captured_ctx.skip_reproduction is True
    assert captured_ctx.failure_reason == "REPLACEMENT_PROSE_CONTAMINATION"
    assert captured_ctx.python_executable == "/tmp/task-venv/bin/python"
    assert "contained prose or commentary" in captured_ctx.user_prompt


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
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
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


# ---------------------------------------------------------------------------
# C7: Output Classification Tests
# ---------------------------------------------------------------------------

def test_patch_synthesis_records_output_classification() -> None:
    from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
    from nexus.services.local_heal.patcher import Patcher
    from nexus.services.local_heal.interface import PatchSynthesisInput, LocalizedFile
    from unittest.mock import patch, MagicMock
    from nexus.services.local_heal.micro_verifier import MicroVerifyResult

    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()

    class MockLLM:
        def generate(self, **kwargs):
            return "Some explanation\n<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"

    phase = PatchSynthesisPhase(parser, patcher, llm_client=MockLLM())
    inp = PatchSynthesisInput(
        instance_id="test",
        problem_statement="test",
        repro_evidence="test",
        plan=None,
        localized_files=[LocalizedFile(path="file.py", content="old\n")],
        repo_dir=Path("/tmp"),
        reasoning_mode="INTUITIVE",
        attempt=1,
        max_tries=1,
    )

    # Mock apply + micro verifier so we can assert C7 telemetry without changing runtime control.
    from nexus.services.local_heal.patch_applier import PatchApplicationResult
    mock_apply = MagicMock(return_value=PatchApplicationResult(
        success=True,
        applied_diffs=["+++ b/file.py\nnew\n"],
        error_reason="",
    ))
    with patch.object(phase.patch_applier, "apply_and_validate", mock_apply), \
         patch("nexus.services.local_heal.micro_verifier.MicroVerifier.verify") as mock_v:
        mock_v.return_value = MicroVerifyResult(
            passed=True, syntax_ok=True, import_ok=True, task_scoped=False
        )
        output = phase.run(inp)
        assert output.success is True

        preflight = output.preflight_telemetry
        assert preflight.get("output_class") == "VALID_SEARCH_REPLACE"
        assert preflight.get("contains_search_marker") is True
        assert preflight.get("contains_replace_marker") is True
        assert preflight.get("contains_markdown_fence") is False
        assert preflight.get("contains_unified_diff_header") is False
        assert preflight.get("contains_natural_language_only") is False


def test_patch_synthesis_retry_disables_interleaved_reasoning() -> None:
    from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
    from nexus.services.local_heal.patcher import Patcher
    from nexus.services.local_heal.interface import PatchSynthesisInput, LocalizedFile

    captured = {}

    class MockLLM:
        def generate(self, **kwargs):
            captured["system_prompt"] = kwargs.get("system_prompt", "")
            return ""

    phase = PatchSynthesisPhase(SolidSearchReplaceProtocol(), Patcher(), llm_client=MockLLM())
    inp = PatchSynthesisInput(
        instance_id="retry-test",
        problem_statement="fix test",
        repro_evidence="failed",
        plan=None,
        localized_files=[LocalizedFile(path="file.py", content="old\n")],
        repo_dir=Path("/tmp"),
        reasoning_mode="INTUITIVE",
        attempt=2,
        max_tries=2,
        failure_reason="SEARCH_MISMATCH",
    )

    output = phase.run(inp)

    assert output.success is False
    assert "Before producing the patch, briefly analyze" not in captured["system_prompt"]


def test_m1_row_exposes_output_excerpt_and_class() -> None:
    """C7: output_class and contains_markdown_fence are visible in raw_meta via mocked telemetries."""
    from unittest.mock import patch
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult

    req = make_test_request("c7-telemetry", execution_topology="localheal_pipeline")
    fenced_output = "```\n<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n```"

    with patch(
        "nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute"
    ) as mock_exec:
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="FENCED_OUTPUT_STOP_GATE",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "FENCED_OUTPUT_STOP_GATE",
                "output_class": "FENCED_SEARCH_REPLACE",
                "contains_markdown_fence": True,
                "output_excerpt_first_500": fenced_output[:500],
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: fenced_output))
        meta = resp.raw_model_metadata

        assert meta.get("output_class") == "FENCED_SEARCH_REPLACE"
        assert meta.get("contains_markdown_fence") is True
        assert meta.get("output_excerpt_first_500") == fenced_output[:500]
        assert resp.candidate_patch == ""  # pipeline_final_patch empty → no fallback


def test_output_excerpt_is_bounded() -> None:
    # Excerpt should be bounded to 500 characters
    long_response = "A" * 1000
    req = make_test_request("c7-excerpt-bound", execution_topology="localheal_pipeline")
    provider = InjectedLocalModelProvider(lambda _: long_response)
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    
    assert len(meta.get("output_excerpt_first_500", "")) <= 500


def test_output_classification_does_not_mark_solved() -> None:
    req = make_test_request("c7-solved-check", execution_topology="localheal_pipeline")
    provider = InjectedLocalModelProvider(lambda _: "Some natural language only")
    resp = LocalModelExecutor.run(req, provider=provider)
    meta = resp.raw_model_metadata
    
    assert meta.get("solved") is not True


def test_fence_output_classification_does_not_strip_fences() -> None:
    """C7: fenced output is classified as FENCED_SEARCH_REPLACE and stops candidate projection."""
    from unittest.mock import patch
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult

    req = make_test_request("c7-fenced", execution_topology="localheal_pipeline")
    fenced_output = "```\n<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n```"

    with patch(
        "nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute"
    ) as mock_exec:
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="FENCED_OUTPUT_STOP_GATE",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "FENCED_OUTPUT_STOP_GATE",
                "output_class": "FENCED_SEARCH_REPLACE",
                "contains_markdown_fence": True,
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: fenced_output))
        assert resp.raw_model_metadata.get("output_class") == "FENCED_SEARCH_REPLACE"
        assert resp.candidate_patch == ""  # C9: no fallback, empty stays empty


# ---------------------------------------------------------------------------
# C8: Recovery quarantine tests
# ---------------------------------------------------------------------------

def test_verifier_command_is_quarantined_during_c7_recovery() -> None:
    from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
    from nexus.services.local_heal.patcher import Patcher
    from nexus.services.local_heal.interface import PatchSynthesisInput, LocalizedFile
    from unittest.mock import patch, MagicMock
    from nexus.services.local_heal.micro_verifier import MicroVerifyResult
    from nexus.services.local_heal.patch_applier import PatchApplicationResult

    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()

    class MockLLM:
        def generate(self, **kwargs):
            return "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"

    phase = PatchSynthesisPhase(parser, patcher, llm_client=MockLLM())

    inp = PatchSynthesisInput(
        instance_id="test",
        problem_statement="test",
        repro_evidence="test",
        plan=None,
        localized_files=[LocalizedFile(path="file.py", content="old\n")],
        repo_dir=Path("/tmp"),
        reasoning_mode="INTUITIVE",
        attempt=1,
        max_tries=1,
    )
    object.__setattr__(inp, "route_context", {
        "verifier_command": ["python3", "verify.py"]
    })

    mock_apply = MagicMock(return_value=PatchApplicationResult(
        success=True,
        applied_diffs=["+++ b/file.py\nnew\n"],
        error_reason="",
    ))
    with patch.object(phase.patch_applier, "apply_and_validate", mock_apply), \
         patch("nexus.services.local_heal.micro_verifier.MicroVerifier.verify") as mock_v:
        mock_v.return_value = MicroVerifyResult(
            passed=True, syntax_ok=True, import_ok=True, task_scoped=True
        )
        output = phase.run(inp)
        assert output.success is True
        assert output.preflight_telemetry.get("micro_verify_context_present") is None
        assert output.preflight_telemetry.get("verifier_command_present") is None



def test_missing_verifier_command_does_not_change_patch_synthesis_control_flow() -> None:
    from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase
    from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
    from nexus.services.local_heal.patcher import Patcher
    from nexus.services.local_heal.interface import PatchSynthesisInput, LocalizedFile
    from unittest.mock import patch, MagicMock
    from nexus.services.local_heal.micro_verifier import MicroVerifyResult

    parser = SolidSearchReplaceProtocol()
    patcher = Patcher()

    class MockLLM:
        def generate(self, **kwargs):
            return "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"

    phase = PatchSynthesisPhase(parser, patcher, llm_client=MockLLM())
    inp = PatchSynthesisInput(
        instance_id="test",
        problem_statement="test",
        repro_evidence="test",
        plan=None,
        localized_files=[LocalizedFile(path="file.py", content="old\n")],
        repo_dir=Path("/tmp"),
        reasoning_mode="INTUITIVE",
        attempt=1,
        max_tries=1,
    )
    from nexus.services.local_heal.patch_applier import PatchApplicationResult
    mock_apply = MagicMock(return_value=PatchApplicationResult(
        success=True,
        applied_diffs=["+++ b/file.py\nnew\n"],
        error_reason="",
    ))
    with patch.object(phase.patch_applier, "apply_and_validate", mock_apply), \
         patch("nexus.services.local_heal.micro_verifier.MicroVerifier.verify") as mock_v:
        mock_v.return_value = MicroVerifyResult(
            passed=True, syntax_ok=True, import_ok=True, task_scoped=False
        )
        output = phase.run(inp)
        assert output.success is True
        assert output.preflight_telemetry.get("bare_python_rejected") is None


def test_micro_verify_context_fields_remain_unset_during_recovery() -> None:
    req = make_test_request("c8-context-present", execution_topology="localheal_pipeline")
    req.route_context["verifier_command"] = ["python3", "verify.py"]
    
    provider = InjectedLocalModelProvider(lambda _: "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n")
    
    from unittest.mock import patch
    from nexus.services.local_heal.micro_verifier import MicroVerifyResult
    with patch("nexus.services.local_heal.micro_verifier.MicroVerifier.verify") as mock_v:
        mock_v.return_value = MicroVerifyResult(
            passed=True, syntax_ok=True, import_ok=True, task_scoped=True
        )
        resp = LocalModelExecutor.run(req, provider=provider)
        meta = resp.raw_model_metadata
        assert meta.get("micro_verify_context_present") is False
        assert meta.get("verifier_command_present") is False


def test_micro_verify_context_fields_default_false_in_executor_projection() -> None:
    from unittest.mock import patch
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult

    req = make_test_request("c8-defaults", execution_topology="localheal_pipeline")

    with patch(
        "nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute"
    ) as mock_exec:
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="MICRO_VERIFY_CONTEXT_MISSING",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "MICRO_VERIFY_CONTEXT_MISSING",
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
        meta = resp.raw_model_metadata

        assert resp.candidate_patch == ""
        assert meta.get("micro_verify_failure_reason") is None


def test_micro_verify_context_does_not_mark_solved_without_verifier_pass() -> None:
    req = make_test_request("c8-no-solved", execution_topology="localheal_pipeline")
    req.route_context["verifier_command"] = ["python3", "verify.py"]
    
    provider = InjectedLocalModelProvider(lambda _: "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n")
    
    from unittest.mock import patch
    from nexus.services.local_heal.micro_verifier import MicroVerifyResult
    with patch("nexus.services.local_heal.micro_verifier.MicroVerifier.verify") as mock_v:
        mock_v.return_value = MicroVerifyResult(
            passed=False, syntax_ok=True, error_message="TEST_FAILURE", task_scoped=True
        )
        resp = LocalModelExecutor.run(req, provider=provider)
        meta = resp.raw_model_metadata
        assert meta.get("solved") is not True


# ---------------------------------------------------------------------------
# C9: Candidate projection and isolation
# ---------------------------------------------------------------------------

def test_non_empty_pipeline_patch_projects_candidate() -> None:
    req = make_test_request(
        "c9-projection",
        evidence_refs=("ref1",),
        execution_topology="localheal_pipeline",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    
    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"
        diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            }
        )
        with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
             patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
            mock_apply.return_value = IsolatedApplyReceipt(
                    task_id="c9-projection",
                    workspace_path="/tmp/ws",
                    target_file="file.py",
                    patch_apply_status="applied",
                    patch_apply_error="",
                    selected_candidate_hash=diff_hash,
                    applied_patch_hash=diff_hash,
                    selected_candidate_hash_matches_applied=True,
                    candidate_output_isolated=True,
                    mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )
            mock_verify.return_value = IsolatedVerifierReceipt(
                task_id="c9-projection",
                verifier_status="pass",
                exit_code=0,
                stdout_tail="",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            )
            resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
        meta = resp.raw_model_metadata
        
        assert meta.get("pipeline_result_projected") is True
        assert resp.candidate_patch == "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"
        assert meta.get("candidate_hash_empty") is False
        assert meta.get("candidate_isolation_attempted") is True
        assert meta.get("candidate_isolated") is True
        assert meta.get("hash_match") is True
        assert meta.get("isolated_verifier_status") == "pass"


def test_empty_pipeline_patch_does_not_project_candidate() -> None:
    req = make_test_request("c9-no-projection", execution_topology="localheal_pipeline")
    
    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "some error",
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
        meta = resp.raw_model_metadata
        
        assert meta.get("pipeline_result_projected") is False
        assert resp.candidate_patch == ""
        assert meta.get("candidate_hash_empty") is True


def test_pipeline_patch_enters_isolation() -> None:
    req = make_test_request(
        "c9-isolation",
        evidence_refs=("ref1",),
        execution_topology="localheal_pipeline",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    
    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n",
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            }
        )
        with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
             patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
            mock_apply.return_value = IsolatedApplyReceipt(
                task_id="c9-isolation",
                workspace_path="/tmp/ws",
                target_file="file.py",
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash="candidate-hash",
                applied_patch_hash="candidate-hash",
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )
            mock_verify.return_value = IsolatedVerifierReceipt(
                task_id="c9-isolation",
                verifier_status="pass",
                exit_code=0,
                stdout_tail="",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            )
            resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
        meta = resp.raw_model_metadata
        
        assert meta.get("candidate_isolation_attempted") is True
        assert meta.get("candidate_isolated") is True


def test_candidate_hash_empty_blocks_solved() -> None:
    req = make_test_request("c9-hash-empty-blocks", execution_topology="localheal_pipeline")
    resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
    meta = resp.raw_model_metadata
    
    assert meta.get("candidate_hash_empty") is True
    assert meta.get("solved") is not True


def test_hash_match_required_for_solved() -> None:
    req = make_test_request(
        "c9-hash-match",
        evidence_refs=("ref1",),
        execution_topology="localheal_pipeline",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    
    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n",
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            }
        )
        with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
             patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
            mock_apply.return_value = IsolatedApplyReceipt(
                task_id="c9-hash-match",
                workspace_path="/tmp/ws",
                target_file="file.py",
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash="candidate-hash",
                applied_patch_hash="different-hash",
                selected_candidate_hash_matches_applied=False,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )
            mock_verify.return_value = IsolatedVerifierReceipt(
                task_id="c9-hash-match",
                verifier_status="pass",
                exit_code=0,
                stdout_tail="",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            )
            resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
        meta = resp.raw_model_metadata
        
        assert meta.get("hash_match") is False
        assert meta.get("solved") is not True


def test_pipeline_projection_restores_original_target_before_isolated_apply(tmp_path) -> None:
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    original_text = "def double(x):\n    return x * 2\n"
    target_path.write_text(original_text, encoding="utf-8")

    req = make_test_request(
        "c9-restore-before-apply",
        repo_root=str(tmp_path),
        target_file=target_rel,
        evidence_refs=("ref1",),
        execution_topology="localheal_pipeline",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )

    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1,2 +1,2 @@\n-def double(x):\n-    return x * 2\n+def double(x):\n+    return x * 3\n"

    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt

        def _mutating_execute(_ctx):
            target_path.write_text("def mutated():\n    return 999\n", encoding="utf-8")
            return CapabilityExecutionResult(
                name="repair_loop",
                selected=True,
                invoked=True,
                gate_passed=True,
                outcome_contributed=True,
                evidence_present=True,
                failure_reason="",
                telemetries={
                    "pipeline_final_patch": diff_text,
                    "pipeline_solve_eligible": True,
                    "pipeline_failure_reason": "",
                    "model_called": True,
                },
            )

        mock_exec.side_effect = _mutating_execute

        def _check_apply(apply_req):
            assert target_path.read_text(encoding="utf-8") == original_text
            return IsolatedApplyReceipt(
                task_id="c9-restore-before-apply",
                workspace_path="/tmp/ws",
                target_file=target_rel,
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash=hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
                applied_patch_hash=hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )

        with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=_check_apply), \
             patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
            mock_verify.return_value = IsolatedVerifierReceipt(
                task_id="c9-restore-before-apply",
                verifier_status="pass",
                exit_code=0,
                stdout_tail="",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            )
            resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("candidate_isolated") is True
    assert meta.get("hash_match") is True
    assert meta.get("isolated_verifier_status") == "pass"


def test_pipeline_projection_drops_non_target_file_diffs_before_isolated_apply() -> None:
    req = make_test_request(
        "c9-target-only-projection",
        evidence_refs=("ref1",),
        execution_topology="localheal_pipeline",
        target_file="toy/math_util.py",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )

    full_diff = (
        "--- a/verify_math.py\n"
        "+++ b/verify_math.py\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')\n"
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def double(x):\n"
        "-    return x * 2\n"
        "+def double(x):\n"
        "+    return x * 3\n"
    )
    target_only_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def double(x):\n"
        "-    return x * 2\n"
        "+def double(x):\n"
        "+    return x * 3\n"
    )
    target_hash = hashlib.sha256(target_only_diff.rstrip("\n").encode("utf-8")).hexdigest()

    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop",
            selected=True,
            invoked=True,
            gate_passed=True,
            outcome_contributed=True,
            evidence_present=True,
            failure_reason="",
            telemetries={
                "pipeline_final_patch": full_diff,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            },
        )

        def _check_apply(apply_req):
            assert apply_req.unified_diff == target_only_diff.rstrip("\n")
            assert apply_req.selected_candidate_hash == target_hash
            return IsolatedApplyReceipt(
                task_id="c9-target-only-projection",
                workspace_path="/tmp/ws",
                target_file="toy/math_util.py",
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash=target_hash,
                applied_patch_hash=target_hash,
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )

        with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=_check_apply), \
             patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
            mock_verify.return_value = IsolatedVerifierReceipt(
                task_id="c9-target-only-projection",
                verifier_status="pass",
                exit_code=0,
                stdout_tail="",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            )
            resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert resp.candidate_patch == target_only_diff.rstrip("\n")
    assert meta.get("protocol_normalization", {}).get("normalized") is True
    assert meta.get("protocol_normalization", {}).get("dropped_files") == ["verify_math.py"]
    assert meta.get("candidate_isolated") is True
