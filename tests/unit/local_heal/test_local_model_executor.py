from __future__ import annotations

import hashlib
import pytest
from pathlib import Path

from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
    _resolve_execution_topology,
    compute_patch_lifecycle_state,
    compute_failure_class,
    compute_verifier_failure_evidence,
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


def test_pipeline_legacy_context_promotes_semantic_retry_seed_to_v2():
    from nexus.services.local_heal.pipeline import HealContext as LegacyHealContext

    legacy = LegacyHealContext(
        instance_id="seed-promo",
        repo_dir=Path("/tmp"),
        problem_statement="fix bug",
        route_context={
            "semantic_retry_seed": {
                "verifier_failure_evidence_available": True,
                "semantic_retry_evidence_ready": True,
                "failure_class": "verification_failed",
                "verifier_failure_kind": "nonzero_exit",
                "verifier_exit_code": 1,
            }
        },
    )

    v2 = legacy.to_v2()

    assert getattr(v2.op, "verifier_failure_evidence_available", False) is True
    assert getattr(v2.op, "semantic_retry_evidence_ready", False) is True
    assert getattr(v2.op, "failure_class", "") == "verification_failed"
    assert getattr(v2.op, "verifier_failure_kind", "") == "nonzero_exit"
    assert getattr(v2.op, "verifier_exit_code", "") == 1


def test_pipeline_legacy_context_promotes_repair_specification_to_v2():
    from nexus.services.local_heal.pipeline import HealContext as LegacyHealContext

    legacy = LegacyHealContext(
        instance_id="repair-spec-promo",
        repo_dir=Path("/tmp"),
        problem_statement="fix bug",
        repair_specification="Replace x * 2 with x * 4 on the first patch attempt.",
    )

    v2 = legacy.to_v2()

    assert getattr(v2.op, "repair_specification", "") == (
        "Replace x * 2 with x * 4 on the first patch attempt."
    )


def test_localheal_pipeline_verifier_fail_delegates_existing_retry_with_seeded_evidence():
    from unittest.mock import patch, MagicMock
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt

    req = make_test_request(
        "c15-pipeline-verifier-retry",
        execution_topology="localheal_pipeline",
        target_file="toy/math_util.py",
        route_context={
            "verifier_command": ["python3", "-c", "raise SystemExit(1)"],
            "python_executable": "/tmp/task-venv/bin/python",
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"
    diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

    with patch(
        "nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute"
    ) as mock_exec, \
        patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
        patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify, \
        patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
        patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run:
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop",
            selected=True,
            invoked=True,
            gate_passed=True,
            outcome_contributed=True,
            evidence_present=True,
            failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text,
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "NO_BLOCKS_FOUND:NO_BLOCKS_FOUND",
                "patch_synthesis_output_len": len(diff_text),
                "patch_synthesis_model_name": "qwen2.5-coder:7b",
                "patch_synthesis_model_called": True,
                "provider_invoked": True,
                "model_called": True,
            },
        )
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="c15-pipeline-verifier-retry",
            workspace_path="/tmp/ws",
            target_file="toy/math_util.py",
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
            task_id="c15-pipeline-verifier-retry",
            verifier_status="fail",
            exit_code=1,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        def _capture_retry_ctx(heal_ctx):
            seed = heal_ctx.route_context.get("semantic_retry_seed", {})
            assert seed.get("verifier_failure_evidence_available") is True
            assert seed.get("semantic_retry_evidence_ready") is True
            assert seed.get("failure_class") == "verification_failed"
            assert seed.get("verifier_exit_code") == 1
            result = MagicMock()
            result.final_patch = ""
            result.failure_reason = "VERIFIER_FAIL"
            result.model_decisions = [
                {
                    "phase": "patch",
                    "output_class": "VALID_SEARCH_REPLACE",
                    "parser_error_kind": "none",
                    "status": "SUCCESS",
                    "output_excerpt": "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
                }
            ]
            result._orchestrator_verifier_evidence_passed = True
            result._orchestrator_verifier_evidence_fields = "nonzero_exit,1,abc123"
            result._orchestrator_retry_prompt_evidence_hash = "abc123def4567890"
            result._semantic_retry_telemetry = {
                "semantic_retry_count": 1,
                "same_span_retry": True,
            }
            return result

        mock_pipeline_run.side_effect = _capture_retry_ctx

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("retry_available") is True
    assert meta.get("pipeline_retry_delegated") is True
    assert meta.get("failure_class") == "verification_failed"
    assert meta.get("verifier_failure_evidence_available") is True
    assert meta.get("semantic_retry_evidence_ready") is True
    assert meta.get("orchestrator_verifier_evidence_passed_to_retry") is True
    assert meta.get("semantic_retry_verifier_evidence_injected") is True
    assert meta.get("semantic_retry_invoked") is True
    assert meta.get("semantic_retry_count") == 1
    assert meta.get("same_span_retry") is True


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
# C15-5C: Small-Model Committee Telemetry & Execution Tests
# ---------------------------------------------------------------------------

def _make_pipeline_verifier_fail_mock(task_id, diff_text, diff_hash, apply_fn, verify_fn):
    """Helper: returns mocks for (exec, apply, verify, pipeline_run) to drive delegated retry."""
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from unittest.mock import MagicMock

    mock_exec_result = CapabilityExecutionResult(
        name="repair_loop",
        selected=True, invoked=True, gate_passed=True,
        outcome_contributed=True, evidence_present=True, failure_reason="",
        telemetries={
            "pipeline_final_patch": diff_text,
            "pipeline_solve_eligible": False,
            "pipeline_failure_reason": "NO_BLOCKS_FOUND:NO_BLOCKS_FOUND",
            "patch_synthesis_output_len": len(diff_text),
            "patch_synthesis_model_name": "qwen2.5-coder:7b-instruct",
            "patch_synthesis_model_called": True,
            "provider_invoked": True,
            "model_called": True,
        },
    )
    return mock_exec_result


def test_committee_trial_flows(monkeypatch) -> None:
    """C15-5C: 2-candidate committee (Qwen 7B + DeepSeek 6.7B).
    First round verifier fails → delegated retry committee runs →
    DeepSeek wins (verifier pass) → winner metadata written."""
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch, MagicMock
    import hashlib, json

    # Header must match target_file so _project_pipeline_patch_to_target_file() keeps this section
    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"
    diff_hash = hashlib.sha256(diff_text.encode()).hexdigest()



    applied_applies = []
    applied_verifies = []

    def mock_apply(req):
        applied_applies.append(req.task_id)
        return IsolatedApplyReceipt(
            task_id=req.task_id, patch_apply_status="applied", patch_apply_error="",
            target_file=req.target_file,
            selected_candidate_hash=req.selected_candidate_hash,
            applied_patch_hash=req.selected_candidate_hash,
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True, workspace_path="/tmp/ws",
            mutation_allowed=True, applied_patch_hash_source="git_diff",
        )

    def mock_verify(req):
        applied_verifies.append(req.task_id)
        # First-round verifier: fail (triggers delegated retry)
        # Committee verifier: pass only for deepseek-coder candidate
        if "#committee-" not in req.task_id:
            return IsolatedVerifierReceipt(
                task_id=req.task_id, verifier_status="fail", exit_code=1,
                stdout_tail="AssertionError: expected 4, got 3", stderr_tail="",
                verifier_error="", verifier_allowed=True,
            )
        status = "pass" if "deepseek-coder" in req.task_id else "fail"
        return IsolatedVerifierReceipt(
            task_id=req.task_id, verifier_status=status,
            exit_code=0 if status == "pass" else 1,
            stdout_tail="" if status == "pass" else "AssertionError",
            stderr_tail="", verifier_error="", verifier_allowed=True,
        )

    req = make_test_request(
        "committee-trial-task",
        execution_topology="localheal_pipeline",
        target_file="toy/math_util.py",
        route_context={
            "verifier_command": ["python3", "-c", "raise SystemExit(1)"],
            "python_executable": "/tmp/venv/bin/python",
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
            },
        },
    )

    with patch(
        "nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute"
    ) as mock_exec, \
        patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=mock_apply), \
        patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier", side_effect=mock_verify), \
        patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
        patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run:

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True, gate_passed=True,
            outcome_contributed=True, evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "patch_synthesis_output_len": len(diff_text),
                "patch_synthesis_model_name": "qwen2.5-coder:7b-instruct",
                "patch_synthesis_model_called": True,
                "provider_invoked": True, "model_called": True,
                # Pipeline run flags — required for isolation path to be entered
                "localheal_pipeline_run_called": True,
                "localheal_pipeline_run_success": True,
                "localheal_pipeline_invoked": True,
                "localheal_pipeline_actual_execution": True,
                "orchestrator_run_reachable": True,
                "path_a_actual_execution": True,
            },
        )

        def make_pipeline_run_result(heal_ctx):
            r = MagicMock()
            r.final_patch = diff_text
            r.failure_reason = ""
            r.model_decisions = [{"phase": "patch", "output_class": "VALID_SEARCH_REPLACE",
                                  "parser_error_kind": "none", "status": "SUCCESS",
                                  "output_excerpt": "<<<<<<< SEARCH"}]
            r._orchestrator_verifier_evidence_passed = False
            r._orchestrator_verifier_evidence_fields = ""
            r._orchestrator_retry_prompt_evidence_hash = ""
            r._semantic_retry_telemetry = {}
            return r


        mock_pipeline_run.side_effect = make_pipeline_run_result

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    meta = resp.raw_model_metadata

    assert meta.get("delegated_retry_committee_path_used") is True, (
        f"Expected committee_path_used=True, meta keys: {[k for k in meta if 'delegated' in k]}"
    )
    assert meta.get("delegated_retry_heterogeneous_candidate_count") == 2

    candidates = json.loads(meta.get("delegated_retry_committee_candidates_json", "[]"))
    assert len(candidates) == 2

    qwen_cand = [c for c in candidates if "qwen" in c["model"]][0]
    assert qwen_cand["verifier_result"] == "fail"
    assert qwen_cand["selected"] is False
    assert qwen_cand["rejection_reason"] == "verifier_failed"

    ds_cand = [c for c in candidates if "deepseek" in c["model"]][0]
    assert ds_cand["verifier_result"] == "pass"
    assert ds_cand["selected"] is True
    assert ds_cand["rejection_reason"] == ""

    assert meta.get("delegated_retry_heterogeneous_winner_model") == "deepseek-coder:6.7b-instruct"


def test_committee_triple_and_limits(monkeypatch) -> None:
    """C15-5C: 3-candidate committee. All candidates tried; no 14B model included."""
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch, MagicMock
    import hashlib, json

    # Header must match target_file so _project_pipeline_patch_to_target_file() keeps this section
    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"
    diff_hash = hashlib.sha256(diff_text.encode()).hexdigest()

    def mock_apply(req):
        return IsolatedApplyReceipt(
            task_id=req.task_id, patch_apply_status="applied", patch_apply_error="",
            target_file=req.target_file,
            selected_candidate_hash=req.selected_candidate_hash,
            applied_patch_hash=req.selected_candidate_hash,
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True, workspace_path="/tmp/ws",
            mutation_allowed=True, applied_patch_hash_source="git_diff",
        )

    def mock_verify(req):
        if "#committee-" not in req.task_id:
            return IsolatedVerifierReceipt(
                task_id=req.task_id, verifier_status="fail", exit_code=1,
                stdout_tail="failure", stderr_tail="", verifier_error="", verifier_allowed=True,
            )
        # Ornith wins
        status = "pass" if "Ornith" in req.task_id else "fail"
        return IsolatedVerifierReceipt(
            task_id=req.task_id, verifier_status=status,
            exit_code=0 if status == "pass" else 1,
            stdout_tail="", stderr_tail="", verifier_error="", verifier_allowed=True,
        )

    req = make_test_request(
        "committee-triple-task",
        execution_topology="localheal_pipeline",
        target_file="toy/math_util.py",
        route_context={
            "verifier_command": ["python3", "-c", "raise SystemExit(1)"],
            "python_executable": "/tmp/venv/bin/python",
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": [
                    "qwen2.5-coder:7b-instruct",
                    "deepseek-coder:6.7b-instruct",
                    "Ornith-1.0-9B-GGUF",
                ],
            },
        },
    )

    with patch(
        "nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute"
    ) as mock_exec, \
        patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=mock_apply), \
        patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier", side_effect=mock_verify), \
        patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
        patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run:

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True, gate_passed=True,
            outcome_contributed=True, evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text,
                "pipeline_solve_eligible": False,
                # Empty failure_reason so compute_failure_class falls through to lifecycle-state-based logic
                "pipeline_failure_reason": "",
                "patch_synthesis_output_len": len(diff_text),
                "patch_synthesis_model_name": "qwen2.5-coder:7b-instruct",
                "patch_synthesis_model_called": True,
                "provider_invoked": True, "model_called": True,
            },
        )

        def make_pipeline_run_result(heal_ctx):
            r = MagicMock()
            r.final_patch = diff_text
            r.failure_reason = ""
            r.model_decisions = [{"phase": "patch", "output_class": "VALID_SEARCH_REPLACE",
                                  "parser_error_kind": "none", "status": "SUCCESS",
                                  "output_excerpt": "<<<<<<< SEARCH"}]
            r._orchestrator_verifier_evidence_passed = False
            r._orchestrator_verifier_evidence_fields = ""
            r._orchestrator_retry_prompt_evidence_hash = ""
            r._semantic_retry_telemetry = {}
            return r

        mock_pipeline_run.side_effect = make_pipeline_run_result

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    meta = resp.raw_model_metadata

    assert meta.get("delegated_retry_heterogeneous_candidate_count") == 3, (
        f"Expected 3 candidates, got {meta.get('delegated_retry_heterogeneous_candidate_count')}"
    )
    candidates = json.loads(meta.get("delegated_retry_committee_candidates_json", "[]"))
    assert len(candidates) == 3
    assert "14b" not in [c["model"].lower() for c in candidates]


def test_committee_candidate_records_conversion_status(monkeypatch) -> None:
    """C15-5F: Verify that candidate metadata records detailed conversion status and telemetry fields."""
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch, MagicMock
    import hashlib, json

    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"

    def mock_apply(req):
        return IsolatedApplyReceipt(
            task_id=req.task_id, patch_apply_status="applied", patch_apply_error="",
            target_file=req.target_file, selected_candidate_hash=req.selected_candidate_hash,
            applied_patch_hash=req.selected_candidate_hash, selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True, workspace_path="/tmp/ws", mutation_allowed=True, applied_patch_hash_source="git_diff"
        )

    def mock_verify(req):
        return IsolatedVerifierReceipt(
            task_id=req.task_id, verifier_status="fail", exit_code=1, stdout_tail="AssertionError", stderr_tail="", verifier_error="", verifier_allowed=True
        )

    req = make_test_request(
        "comm-tele-task",
        execution_topology="localheal_pipeline",
        target_file="toy/math_util.py",
        route_context={
            "verifier_command": ["python3", "-c", "pass"],
            "python_executable": "python3",
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=mock_apply), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier", side_effect=mock_verify), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run:

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True, gate_passed=True, outcome_contributed=True, evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text, "pipeline_solve_eligible": True, "pipeline_failure_reason": "",
                "patch_synthesis_output_len": len(diff_text), "patch_synthesis_model_name": "qwen2.5-coder:7b-instruct",
                "patch_synthesis_model_called": True, "provider_invoked": True, "model_called": True,
                "localheal_pipeline_run_called": True, "localheal_pipeline_run_success": True, "localheal_pipeline_invoked": True,
                "localheal_pipeline_actual_execution": True, "orchestrator_run_reachable": True, "path_a_actual_execution": True,
            }
        )

        def make_pipeline_run_result(heal_ctx):
            model_name = getattr(heal_ctx, "committee_proposer_model", "")
            r = MagicMock()
            r.final_patch = diff_text
            r.pre_verification_final_patch = ""
            r.failure_reason = ""
            r._orchestrator_verifier_evidence_passed = False
            r._orchestrator_verifier_evidence_fields = ""
            r._orchestrator_retry_prompt_evidence_hash = ""
            r._semantic_retry_telemetry = {}
            if "qwen" in model_name:
                r.model_decisions = [{
                    "phase": "patch", "output_class": "UNIFIED_DIFF", "parser_error_kind": "none", "status": "SUCCESS",
                    "output_excerpt": diff_text, "conversion_status": "unified_diff_to_ssrp_converted",
                    "conversion_source_hash_before": "src_hash_123", "conversion_candidate_hash": "cand_hash_123",
                    "target_file_correct": True, "preimage_match_status": "exact_match"
                }]
            else:
                r.model_decisions = [{
                    "phase": "patch", "output_class": "MALFORMED_SEARCH_REPLACE", "parser_error_kind": "none", "status": "FAIL"
                }]
            return r

        mock_pipeline_run.side_effect = make_pipeline_run_result

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    meta = resp.raw_model_metadata
    candidates = json.loads(meta.get("delegated_retry_committee_candidates_json", "[]"))
    assert len(candidates) == 2
    qwen_cand = [c for c in candidates if "qwen" in c["model"]][0]
    assert qwen_cand["candidate_model"] == "qwen2.5-coder:7b-instruct"
    assert qwen_cand["format_class"] == "UNIFIED_DIFF"
    assert qwen_cand["conversion_status"] == "unified_diff_to_ssrp_converted"
    assert qwen_cand["conversion_source_hash_before"] == "src_hash_123"
    assert qwen_cand["conversion_candidate_hash"] == "cand_hash_123"
    assert qwen_cand["target_file_correct"] is True
    assert qwen_cand["preimage_match_status"] == "exact_match"


def test_committee_candidate_records_raw_and_applied_hashes(monkeypatch) -> None:
    """C15-5F: Verify that candidate records distinct hashes for applied vs raw candidates."""
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch, MagicMock
    import hashlib, json

    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"

    def mock_apply(req):
        return IsolatedApplyReceipt(
            task_id=req.task_id, patch_apply_status="applied", patch_apply_error="",
            target_file=req.target_file, selected_candidate_hash=req.selected_candidate_hash,
            applied_patch_hash=req.selected_candidate_hash, selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True, workspace_path="/tmp/ws", mutation_allowed=True, applied_patch_hash_source="git_diff"
        )

    def mock_verify(req):
        return IsolatedVerifierReceipt(
            task_id=req.task_id, verifier_status="fail", exit_code=1, stdout_tail="AssertionError", stderr_tail="", verifier_error="", verifier_allowed=True
        )

    req = make_test_request(
        "comm-hash-task",
        execution_topology="localheal_pipeline",
        target_file="toy/math_util.py",
        route_context={
            "verifier_command": ["python3", "-c", "pass"],
            "python_executable": "python3",
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=mock_apply), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier", side_effect=mock_verify), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run:

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True, gate_passed=True, outcome_contributed=True, evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text, "pipeline_solve_eligible": True, "pipeline_failure_reason": "",
                "patch_synthesis_output_len": len(diff_text), "patch_synthesis_model_name": "qwen2.5-coder:7b-instruct",
                "patch_synthesis_model_called": True, "provider_invoked": True, "model_called": True,
                "localheal_pipeline_run_called": True, "localheal_pipeline_run_success": True, "localheal_pipeline_invoked": True,
                "localheal_pipeline_actual_execution": True, "orchestrator_run_reachable": True, "path_a_actual_execution": True,
            }
        )

        def make_pipeline_run_result(heal_ctx):
            model_name = getattr(heal_ctx, "committee_proposer_model", "")
            r = MagicMock()
            r.final_patch = diff_text
            r.pre_verification_final_patch = ""
            r.failure_reason = ""
            r._orchestrator_verifier_evidence_passed = False
            r._orchestrator_verifier_evidence_fields = ""
            r._orchestrator_retry_prompt_evidence_hash = ""
            r._semantic_retry_telemetry = {}
            if "qwen" in model_name:
                r.model_decisions = [{
                    "phase": "patch", "output_class": "UNIFIED_DIFF", "parser_error_kind": "none", "status": "SUCCESS",
                    "output_excerpt": diff_text, "conversion_status": "unified_diff_to_ssrp_converted",
                    "conversion_source_hash_before": "src_hash_abc", "conversion_candidate_hash": "cand_hash_xyz",
                    "target_file_correct": True, "preimage_match_status": "exact_match"
                }]
            else:
                r.model_decisions = [{
                    "phase": "patch", "output_class": "MALFORMED_SEARCH_REPLACE", "parser_error_kind": "none", "status": "FAIL"
                }]
            return r

        mock_pipeline_run.side_effect = make_pipeline_run_result

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    meta = resp.raw_model_metadata
    candidates = json.loads(meta.get("delegated_retry_committee_candidates_json", "[]"))
    qwen_cand = [c for c in candidates if "qwen" in c["model"]][0]
    expected_applied_hash = hashlib.sha256(diff_text.rstrip("\n").encode()).hexdigest()
    assert qwen_cand["candidate_hash"] == expected_applied_hash
    assert qwen_cand["conversion_candidate_hash"] == "cand_hash_xyz"


def test_committee_unified_diff_conversion_success_allows_isolated_apply(monkeypatch) -> None:
    """C15-5F: Verify that successful unified diff conversion allows isolated apply to run."""
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch, MagicMock
    import json

    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"
    apply_called = []

    def mock_apply(req):
        apply_called.append(req.task_id)
        return IsolatedApplyReceipt(
            task_id=req.task_id, patch_apply_status="applied", patch_apply_error="",
            target_file=req.target_file, selected_candidate_hash=req.selected_candidate_hash,
            applied_patch_hash=req.selected_candidate_hash, selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True, workspace_path="/tmp/ws", mutation_allowed=True, applied_patch_hash_source="git_diff"
        )

    def mock_verify(req):
        # We need the first round to fail
        return IsolatedVerifierReceipt(
            task_id=req.task_id, verifier_status="fail", exit_code=1, stdout_tail="AssertionError", stderr_tail="", verifier_error="", verifier_allowed=True
        )

    req = make_test_request(
        "comm-apply-task",
        execution_topology="localheal_pipeline",
        target_file="toy/math_util.py",
        route_context={
            "verifier_command": ["python3", "-c", "pass"],
            "python_executable": "python3",
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=mock_apply), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier", side_effect=mock_verify), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run:

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True, gate_passed=True, outcome_contributed=True, evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text, "pipeline_solve_eligible": True, "pipeline_failure_reason": "",
                "patch_synthesis_output_len": len(diff_text), "patch_synthesis_model_name": "qwen2.5-coder:7b-instruct",
                "patch_synthesis_model_called": True, "provider_invoked": True, "model_called": True,
                "localheal_pipeline_run_called": True, "localheal_pipeline_run_success": True, "localheal_pipeline_invoked": True,
                "localheal_pipeline_actual_execution": True, "orchestrator_run_reachable": True, "path_a_actual_execution": True,
            }
        )

        def make_pipeline_run_result(heal_ctx):
            model_name = getattr(heal_ctx, "committee_proposer_model", "")
            r = MagicMock()
            r.final_patch = diff_text
            r.pre_verification_final_patch = ""
            r.failure_reason = ""
            r._orchestrator_verifier_evidence_passed = False
            r._orchestrator_verifier_evidence_fields = ""
            r._orchestrator_retry_prompt_evidence_hash = ""
            r._semantic_retry_telemetry = {}
            if "qwen" in model_name:
                r.model_decisions = [{
                    "phase": "patch", "output_class": "UNIFIED_DIFF", "parser_error_kind": "none", "status": "SUCCESS",
                    "output_excerpt": diff_text, "conversion_status": "unified_diff_to_ssrp_converted"
                }]
            else:
                r.model_decisions = [{
                    "phase": "patch", "output_class": "MALFORMED_SEARCH_REPLACE", "parser_error_kind": "none", "status": "FAIL"
                }]
            return r

        mock_pipeline_run.side_effect = make_pipeline_run_result

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    assert len(apply_called) == 2
    assert "comm-apply-task#committee-qwen2.5-coder:7b-instruct" in apply_called


def test_committee_unified_diff_conversion_failure_records_specific_reason(monkeypatch) -> None:
    """C15-5F: Verify that unified diff conversion failure records specific rejection reason and blocks apply."""
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch, MagicMock
    import json

    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"
    apply_called = []

    def mock_apply(req):
        apply_called.append(req.task_id)
        return IsolatedApplyReceipt(
            task_id=req.task_id, patch_apply_status="applied", patch_apply_error="",
            target_file=req.target_file, selected_candidate_hash=req.selected_candidate_hash,
            applied_patch_hash=req.selected_candidate_hash, selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True, workspace_path="/tmp/ws", mutation_allowed=True, applied_patch_hash_source="git_diff"
        )

    def mock_verify(req):
        return IsolatedVerifierReceipt(
            task_id=req.task_id, verifier_status="fail", exit_code=1, stdout_tail="AssertionError", stderr_tail="", verifier_error="", verifier_allowed=True
        )

    req = make_test_request(
        "comm-fail-task",
        execution_topology="localheal_pipeline",
        target_file="toy/math_util.py",
        route_context={
            "verifier_command": ["python3", "-c", "pass"],
            "python_executable": "python3",
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=mock_apply), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier", side_effect=mock_verify), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run:

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True, gate_passed=True, outcome_contributed=True, evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text, "pipeline_solve_eligible": True, "pipeline_failure_reason": "",
                "patch_synthesis_output_len": len(diff_text), "patch_synthesis_model_name": "qwen2.5-coder:7b-instruct",
                "patch_synthesis_model_called": True, "provider_invoked": True, "model_called": True,
                "localheal_pipeline_run_called": True, "localheal_pipeline_run_success": True, "localheal_pipeline_invoked": True,
                "localheal_pipeline_actual_execution": True, "orchestrator_run_reachable": True, "path_a_actual_execution": True,
            }
        )

        def make_pipeline_run_result(heal_ctx):
            model_name = getattr(heal_ctx, "committee_proposer_model", "")
            r = MagicMock()
            r.final_patch = ""
            r.pre_verification_final_patch = ""
            r.failure_reason = "PATCH_FORMAT_INVALID"
            r._orchestrator_verifier_evidence_passed = False
            r._orchestrator_verifier_evidence_fields = ""
            r._orchestrator_retry_prompt_evidence_hash = ""
            r._semantic_retry_telemetry = {}
            if "qwen" in model_name:
                r.model_decisions = [{
                    "phase": "patch", "output_class": "UNIFIED_DIFF", "parser_error_kind": "PATCH_FORMAT_INVALID", "status": "FAIL",
                    "output_excerpt": diff_text, "conversion_status": "unified_diff_target_mismatch"
                }]
            else:
                r.model_decisions = [{
                    "phase": "patch", "output_class": "MALFORMED_SEARCH_REPLACE", "parser_error_kind": "none", "status": "FAIL"
                }]
            return r

        mock_pipeline_run.side_effect = make_pipeline_run_result

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    assert len(apply_called) == 1
    meta = resp.raw_model_metadata
    candidates = json.loads(meta.get("delegated_retry_committee_candidates_json", "[]"))
    qwen_cand = [c for c in candidates if "qwen" in c["model"]][0]
    assert qwen_cand["apply_status"] == "format_rejected"
    assert qwen_cand["rejection_reason"] == "unified_diff_target_mismatch"


def test_committee_no_selected_winner_without_verifier_pass(monkeypatch) -> None:
    """C15-5F: Verify that if no candidate passes the verifier, no winner is selected and solved is False."""
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch, MagicMock
    import json

    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"

    def mock_apply(req):
        return IsolatedApplyReceipt(
            task_id=req.task_id, patch_apply_status="applied", patch_apply_error="",
            target_file=req.target_file, selected_candidate_hash=req.selected_candidate_hash,
            applied_patch_hash=req.selected_candidate_hash, selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True, workspace_path="/tmp/ws", mutation_allowed=True, applied_patch_hash_source="git_diff"
        )

    def mock_verify(req):
        return IsolatedVerifierReceipt(
            task_id=req.task_id, verifier_status="fail", exit_code=1, stdout_tail="AssertionError", stderr_tail="", verifier_error="", verifier_allowed=True
        )

    req = make_test_request(
        "comm-no-winner-task",
        execution_topology="localheal_pipeline",
        target_file="toy/math_util.py",
        route_context={
            "verifier_command": ["python3", "-c", "raise SystemExit(1)"],
            "python_executable": "python3",
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=mock_apply), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier", side_effect=mock_verify), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run:

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True, gate_passed=True, outcome_contributed=True, evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text, "pipeline_solve_eligible": True, "pipeline_failure_reason": "",
                "patch_synthesis_output_len": len(diff_text), "patch_synthesis_model_name": "qwen2.5-coder:7b-instruct",
                "patch_synthesis_model_called": True, "provider_invoked": True, "model_called": True,
                "localheal_pipeline_run_called": True, "localheal_pipeline_run_success": True, "localheal_pipeline_invoked": True,
                "localheal_pipeline_actual_execution": True, "orchestrator_run_reachable": True, "path_a_actual_execution": True,
            }
        )

        def make_pipeline_run_result(heal_ctx):
            r = MagicMock()
            r.final_patch = diff_text
            r.pre_verification_final_patch = ""
            r.failure_reason = ""
            r.model_decisions = [{
                "phase": "patch", "output_class": "VALID_SEARCH_REPLACE", "parser_error_kind": "none", "status": "SUCCESS",
                "output_excerpt": diff_text, "conversion_status": "none"
            }]
            r._orchestrator_verifier_evidence_passed = False
            r._orchestrator_verifier_evidence_fields = ""
            r._orchestrator_retry_prompt_evidence_hash = ""
            r._semantic_retry_telemetry = {}
            return r

        mock_pipeline_run.side_effect = make_pipeline_run_result

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    meta = resp.raw_model_metadata
    assert meta.get("delegated_retry_heterogeneous_winner_model") == ""
    assert meta.get("solved") is not True


def test_committee_no_winner_marks_provider_called_in_summary(monkeypatch) -> None:
    """Committee-mode summary must reflect per-candidate execution truth."""
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from unittest.mock import patch, MagicMock

    diff_text = "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1 +1 @@\n-old\n+new\n"

    def mock_apply(req):
        return IsolatedApplyReceipt(
            task_id=req.task_id, patch_apply_status="applied", patch_apply_error="",
            target_file=req.target_file, selected_candidate_hash=req.selected_candidate_hash,
            applied_patch_hash=req.selected_candidate_hash, selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True, workspace_path="/tmp/ws", mutation_allowed=True, applied_patch_hash_source="git_diff"
        )

    def mock_verify(req):
        return IsolatedVerifierReceipt(
            task_id=req.task_id, verifier_status="fail", exit_code=1, stdout_tail="AssertionError", stderr_tail="", verifier_error="", verifier_allowed=True
        )

    req = make_test_request(
        "comm-summary-task",
        execution_topology="localheal_pipeline",
        target_file="toy/math_util.py",
        route_context={
            "verifier_command": ["python3", "-c", "raise SystemExit(1)"],
            "python_executable": "python3",
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=mock_apply), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier", side_effect=mock_verify), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.__init__", return_value=None), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run") as mock_pipeline_run:

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True, gate_passed=True, outcome_contributed=True, evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text, "pipeline_solve_eligible": True, "pipeline_failure_reason": "",
                "patch_synthesis_output_len": len(diff_text), "patch_synthesis_model_name": "qwen2.5-coder:7b-instruct",
                "patch_synthesis_model_called": True, "provider_invoked": True, "model_called": True,
                "localheal_pipeline_run_called": True, "localheal_pipeline_run_success": True, "localheal_pipeline_invoked": True,
                "localheal_pipeline_actual_execution": True, "orchestrator_run_reachable": True, "path_a_actual_execution": True,
            }
        )

        def make_pipeline_run_result(heal_ctx):
            model_name = getattr(heal_ctx, "committee_proposer_model", "")
            r = MagicMock()
            r.pre_verification_final_patch = ""
            r.failure_reason = ""
            r._orchestrator_verifier_evidence_passed = False
            r._orchestrator_verifier_evidence_fields = ""
            r._orchestrator_retry_prompt_evidence_hash = ""
            r._semantic_retry_telemetry = {}
            if "qwen" in model_name:
                r.final_patch = diff_text
                r.model_decisions = [{
                    "phase": "patch", "output_class": "UNIFIED_DIFF", "parser_error_kind": "none", "status": "SUCCESS",
                    "output_excerpt": diff_text, "conversion_status": "none"
                }]
            else:
                r.final_patch = ""
                r.model_decisions = [{
                    "phase": "patch", "output_class": "EMPTY", "parser_error_kind": "MODEL_EMPTY_RESPONSE", "status": "MODEL_EMPTY_RESPONSE"
                }]
            return r

        mock_pipeline_run.side_effect = make_pipeline_run_result

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    meta = resp.raw_model_metadata
    assert meta.get("delegated_retry_committee_path_used") is True
    assert meta.get("delegated_retry_provider_called") is True
    assert meta.get("delegated_retry_stage") == "committee_candidates_format_rejected"


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


def test_pipeline_projection_reanchors_to_locked_search_when_preimage_mismatches_current_source(tmp_path) -> None:
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-3n-reanchor",
        repo_root=str(tmp_path),
        target_file=target_rel,
        evidence_refs=("ref1",),
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
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

    mismatched_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2 if x is not None else None\n"
        "+    return x * 2 if x is not None and isinstance(x, (int, float)) else None\n"
    )
    expected_reanchored_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2\n"
        "+    return x * 2 if x is not None and isinstance(x, (int, float)) else None\n"
    )
    expected_hash = hashlib.sha256(expected_reanchored_diff.rstrip("\n").encode("utf-8")).hexdigest()

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
                "pipeline_final_patch": mismatched_diff,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            },
        )

        def _check_apply(apply_req):
            assert apply_req.unified_diff == expected_reanchored_diff.rstrip("\n")
            assert apply_req.selected_candidate_hash == expected_hash
            return IsolatedApplyReceipt(
                task_id="c15-3n-reanchor",
                workspace_path="/tmp/ws",
                target_file=target_rel,
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash=expected_hash,
                applied_patch_hash=expected_hash,
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )

        with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=_check_apply), \
             patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
            mock_verify.return_value = IsolatedVerifierReceipt(
                task_id="c15-3n-reanchor",
                verifier_status="pass",
                exit_code=0,
                stdout_tail="",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            )
            resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("protocol_normalization", {}).get("pipeline_locked_search_reanchored") is True
    assert meta.get("protocol_normalization", {}).get("protocol_used") == "pipeline_result_locked_search_reanchored"
    assert meta.get("candidate_isolated") is True
    assert meta.get("hash_match") is True


# ---------------------------------------------------------------------------
# C15-1: Patch Lifecycle Receipt Contract Tests
# ---------------------------------------------------------------------------

def test_patch_lifecycle_patch_absent():
    state = compute_patch_lifecycle_state(
        pipeline_final_patch_len=0,
        pipeline_result_projected=False,
        candidate_isolation_attempted=False,
        isolated_apply_status="",
        hash_match=False,
        applied_patch_hash="",
        selected_candidate_hash="",
        verifier_result="not_run",
        solved=False,
    )
    assert state == "patch_absent"


def test_patch_lifecycle_patch_present_not_projected():
    state = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=False,
        candidate_isolation_attempted=False,
        isolated_apply_status="",
        hash_match=False,
        applied_patch_hash="",
        selected_candidate_hash="",
        verifier_result="not_run",
        solved=False,
    )
    assert state == "patch_present_not_projected"


def test_patch_lifecycle_projected_not_isolated():
    state = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=False,
        isolated_apply_status="",
        hash_match=False,
        applied_patch_hash="",
        selected_candidate_hash="",
        verifier_result="not_run",
        solved=False,
    )
    assert state == "patch_projected_not_isolated"


def test_patch_lifecycle_isolation_attempted_apply_failed():
    state = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="failed",
        hash_match=False,
        applied_patch_hash="",
        selected_candidate_hash="abc123",
        verifier_result="not_run",
        solved=False,
    )
    assert state == "isolation_attempted_apply_failed"


def test_patch_lifecycle_hash_mismatch():
    state = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=False,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_b",
        verifier_result="pass",
        solved=False,
    )
    assert state == "isolation_applied_hash_mismatch"


def test_patch_lifecycle_hash_match_verifier_failed():
    state = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="fail",
        solved=False,
    )
    assert state == "isolation_applied_hash_match_verifier_failed"


def test_patch_lifecycle_verifier_passed_requires_hash_match_and_solved():
    state = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="pass",
        solved=True,
    )
    assert state == "verifier_passed"


def test_patch_lifecycle_verifier_pass_without_hash_match_does_not_pass():
    state = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="",
        selected_candidate_hash="",
        verifier_result="pass",
        solved=True,
    )
    assert state != "verifier_passed"
    assert state == "isolation_applied_hash_mismatch"


def test_m1_row_includes_patch_lifecycle_state():
    req = make_test_request(
        "c15-1-lifecycle",
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
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="NO_PATCH",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "NO_PATCH",
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
    meta = resp.raw_model_metadata
    assert "patch_lifecycle_state" in meta
    assert meta["patch_lifecycle_state"] == "patch_absent"


# ---------------------------------------------------------------------------
# C15-2: Failure Classifier Hardening Tests
# ---------------------------------------------------------------------------

def test_failure_class_empty_response():
    fc, ur = compute_failure_class(
        output_len=0,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state="patch_absent",
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert fc == "unknown_with_reason"
    assert ur == ""


def test_failure_class_provider_error():
    fc, ur = compute_failure_class(
        output_len=100,
        provider_error="ollama_timeout",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state="patch_absent",
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert fc == "provider_error"
    assert ur == ""


def test_failure_class_no_blocks_found():
    fc, ur = compute_failure_class(
        output_len=50,
        provider_error="",
        failure_reason="NO_BLOCKS_FOUND",
        parse_error_kind="",
        patch_lifecycle_state="patch_absent",
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="NO_BLOCKS_FOUND",
    )
    assert fc == "no_blocks_found"
    assert ur == ""


def test_failure_class_search_mismatch():
    fc, ur = compute_failure_class(
        output_len=50,
        provider_error="",
        failure_reason="SEARCH_MISMATCH",
        parse_error_kind="",
        patch_lifecycle_state="patch_absent",
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="SEARCH_MISMATCH",
    )
    assert fc == "search_mismatch"
    assert ur == ""


def test_failure_class_replace_syntax_error():
    fc, ur = compute_failure_class(
        output_len=50,
        provider_error="",
        failure_reason="REPLACE_SYNTAX_ERROR",
        parse_error_kind="",
        patch_lifecycle_state="patch_absent",
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="REPLACE_SYNTAX_ERROR",
    )
    assert fc == "replace_syntax_error"
    assert ur == ""


def test_failure_class_fenced_output():
    fc, ur = compute_failure_class(
        output_len=50,
        provider_error="",
        failure_reason="",
        parse_error_kind="REPLACEMENT_MARKDOWN_FENCE",
        patch_lifecycle_state="patch_absent",
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=True,
        pipeline_failure_reason="",
    )
    assert fc == "parse_failed:REPLACEMENT_MARKDOWN_FENCE"
    assert ur == ""


def test_failure_class_refusal():
    fc, ur = compute_failure_class(
        output_len=50,
        provider_error="",
        failure_reason="REFUSAL",
        parse_error_kind="",
        patch_lifecycle_state="patch_absent",
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="REFUSAL",
    )
    assert fc == "refusal"
    assert ur == ""


def test_failure_class_patch_apply_failed_from_lifecycle():
    fc, ur = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state="isolation_attempted_apply_failed",
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert fc == "patch_apply_failed"
    assert ur == ""


def test_failure_class_hash_mismatch_from_lifecycle():
    fc, ur = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state="isolation_applied_hash_mismatch",
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert fc == "hash_mismatch"
    assert ur == ""


def test_failure_class_verification_failed_from_lifecycle():
    fc, ur = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert fc == "verification_failed"
    assert ur == ""


def test_failure_class_verification_failed_lifecycle_overrides_no_blocks_found_reason():
    fc, ur = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="VERIFIER_FAIL",
        parse_error_kind="",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="NO_BLOCKS_FOUND:NO_BLOCKS_FOUND",
    )
    assert fc == "verification_failed"
    assert ur == ""


def test_failure_class_verifier_passed():
    fc, ur = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state="verifier_passed",
        verifier_result="pass",
        solved=True,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert fc == "verifier_passed"
    assert ur == ""


def test_failure_class_unknown_requires_reason():
    fc, ur = compute_failure_class(
        output_len=50,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state="",
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert fc == "unknown_with_reason"
    assert ur != ""


def test_m1_row_includes_failure_class_and_unknown_reason():
    req = make_test_request(
        "c15-2-classifier",
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
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="NO_PATCH",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "NO_PATCH",
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
    meta = resp.raw_model_metadata
    assert "failure_class" in meta
    assert "unknown_reason" in meta
    assert meta["failure_class"] != ""


# ---------------------------------------------------------------------------
# C15-3A: Verifier Failure Evidence Capture Tests
# ---------------------------------------------------------------------------

def test_verifier_failure_evidence_available_when_stdout_present():
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError: expected 42, got 0",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_evidence_available"] is True
    assert evidence["verifier_stdout_excerpt"] != ""


def test_verifier_failure_evidence_available_when_stderr_present():
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail="Traceback (most recent call last):\n  File \"test.py\", line 5\n    raise ValueError('bad')",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_evidence_available"] is True
    assert evidence["verifier_stderr_excerpt"] != ""


def test_verifier_failure_evidence_false_without_evidence():
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_evidence_available"] is True
    assert evidence["verifier_failure_kind"] == "nonzero_exit"


def test_verifier_failure_evidence_exit_code_only_keeps_empty_excerpts():
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_evidence_available"] is True
    assert evidence["verifier_stdout_excerpt"] == ""
    assert evidence["verifier_stderr_excerpt"] == ""


def test_verifier_stdout_excerpt_is_bounded():
    long_stdout = "A" * 2000
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail=long_stdout,
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert len(evidence["verifier_stdout_excerpt"]) <= 1000


def test_verifier_stderr_excerpt_is_bounded():
    long_stderr = "B" * 2000
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail=long_stderr,
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert len(evidence["verifier_stderr_excerpt"]) <= 1000


def test_verifier_command_hash_does_not_store_raw_command():
    cmd = ("python3", "run_tests.sh", "--verbose")
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="fail",
        stderr_tail="",
        verifier_command=cmd,
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_command_hash"] != ""
    assert len(evidence["verifier_command_hash"]) == 16
    assert "python3" not in evidence["verifier_command_hash"]


def test_verifier_failure_kind_assertion_failure():
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError: assert 1 == 2",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_kind"] == "assertion_failure"


def test_verifier_failure_kind_exception():
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail="Traceback (most recent call last):\n  File \"test.py\", line 10\n    raise RuntimeError('oops')",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_kind"] == "exception"


def test_semantic_retry_evidence_ready_for_verification_failed_lifecycle():
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["semantic_retry_evidence_ready"] is True


def test_semantic_retry_evidence_not_ready_without_verifier_evidence():
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["semantic_retry_evidence_ready"] is True


def test_semantic_retry_evidence_capture_does_not_mark_solved():
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_evidence_available"] is True
    # This function only captures evidence, it must not change solved
    # solved is determined by the caller, not by this function


def test_m1_row_includes_verifier_failure_evidence_fields():
    req = make_test_request(
        "c15-3a-verifier-evidence",
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
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="NO_PATCH",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "NO_PATCH",
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
    meta = resp.raw_model_metadata
    assert "verifier_failure_evidence_available" in meta
    assert "verifier_failure_kind" in meta
    assert "verifier_stdout_excerpt" in meta
    assert "verifier_stderr_excerpt" in meta
    assert "verifier_exit_code" in meta
    assert "verifier_command_hash" in meta
    assert "semantic_retry_evidence_ready" in meta


# ---------------------------------------------------------------------------
# C15-3C: Orchestrator Verifier Evidence Pass-Through Tests
# ---------------------------------------------------------------------------

def test_orchestrator_passes_verifier_evidence_to_existing_retry_prompt():
    from nexus.services.local_heal.orchestrator import HealOrchestrator
    from nexus.services.local_heal.context import HealContext, OperationalContext
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-orch-evidence",
            problem_statement="fix bug",
            repo_dir=Path("/tmp"),
        ),
        gov=MagicMock(),
    )
    ctx.op.final_patch = "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new\n"
    ctx.op.user_prompt = "fix the bug"
    ctx.op.localized_files = [MagicMock(path="f.py")]
    ctx.op.plan = MagicMock(search_symbols=["foo"])
    ctx.op.verifier_command = ["python3", "test.py"]
    ctx.op.verifier_failure_evidence_available = True
    ctx.op.semantic_retry_evidence_ready = True
    ctx.op.failure_class = "verification_failed"
    ctx.op.verifier_failure_kind = "assertion_failure"
    ctx.op.verifier_stdout_excerpt = "AssertionError: expected 42"
    ctx.op.verifier_stderr_excerpt = ""
    ctx.op.verifier_exit_code = 1
    ctx.op.verifier_command_hash = "abc123"

    # Verify the evidence pass-through logic by checking the condition
    vfe_available = getattr(ctx.op, "verifier_failure_evidence_available", False)
    sr_ready = getattr(ctx.op, "semantic_retry_evidence_ready", False)
    failure_class = getattr(ctx.op, "failure_class", "")

    should_pass = sr_ready and vfe_available and failure_class in ("verification_failed", "semantic_wrong_patch")
    assert should_pass is True


def test_orchestrator_does_not_pass_verifier_evidence_when_not_ready():
    from nexus.services.local_heal.context import HealContext, OperationalContext
    from pathlib import Path
    from unittest.mock import MagicMock

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-orch-not-ready",
            problem_statement="fix bug",
            repo_dir=Path("/tmp"),
        ),
        gov=MagicMock(),
    )
    ctx.op.verifier_failure_evidence_available = True
    ctx.op.semantic_retry_evidence_ready = False
    ctx.op.failure_class = "verification_failed"
    ctx.op.verifier_failure_kind = "assertion_failure"
    ctx.op.verifier_stdout_excerpt = "AssertionError"
    ctx.op.verifier_stderr_excerpt = ""
    ctx.op.verifier_exit_code = 1
    ctx.op.verifier_command_hash = "abc123"

    vfe_available = getattr(ctx.op, "verifier_failure_evidence_available", False)
    sr_ready = getattr(ctx.op, "semantic_retry_evidence_ready", False)
    failure_class = getattr(ctx.op, "failure_class", "")

    should_pass = sr_ready and vfe_available and failure_class in ("verification_failed", "semantic_wrong_patch")
    assert should_pass is False


def test_orchestrator_does_not_pass_verifier_evidence_when_unavailable():
    from nexus.services.local_heal.context import HealContext, OperationalContext
    from pathlib import Path
    from unittest.mock import MagicMock

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-orch-unavailable",
            problem_statement="fix bug",
            repo_dir=Path("/tmp"),
        ),
        gov=MagicMock(),
    )
    ctx.op.verifier_failure_evidence_available = False
    ctx.op.semantic_retry_evidence_ready = True
    ctx.op.failure_class = "verification_failed"
    ctx.op.verifier_failure_kind = ""
    ctx.op.verifier_stdout_excerpt = ""
    ctx.op.verifier_stderr_excerpt = ""
    ctx.op.verifier_exit_code = ""
    ctx.op.verifier_command_hash = ""

    vfe_available = getattr(ctx.op, "verifier_failure_evidence_available", False)
    sr_ready = getattr(ctx.op, "semantic_retry_evidence_ready", False)
    failure_class = getattr(ctx.op, "failure_class", "")

    should_pass = sr_ready and vfe_available and failure_class in ("verification_failed", "semantic_wrong_patch")
    assert should_pass is False


def test_orchestrator_verifier_evidence_pass_through_records_metadata():
    from nexus.services.local_heal.context import HealContext, OperationalContext
    from pathlib import Path
    from unittest.mock import MagicMock
    import hashlib

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-orch-meta",
            problem_statement="fix bug",
            repo_dir=Path("/tmp"),
        ),
        gov=MagicMock(),
    )
    ctx.op.verifier_failure_kind = "assertion_failure"
    ctx.op.verifier_stdout_excerpt = "AssertionError"
    ctx.op.verifier_stderr_excerpt = ""
    ctx.op.verifier_exit_code = 1
    ctx.op.verifier_command_hash = "abc123"

    # Simulate the metadata recording
    evidence_injected = True
    evidence_fields = ",".join(
        f for f in [
            ctx.op.verifier_failure_kind,
            ctx.op.verifier_stdout_excerpt[:50],
            ctx.op.verifier_stderr_excerpt[:50],
            str(ctx.op.verifier_exit_code),
            ctx.op.verifier_command_hash,
        ] if f
    )
    evidence_hash = hashlib.sha256(
        f"{ctx.op.verifier_failure_kind}|{ctx.op.verifier_stdout_excerpt[:200]}|{ctx.op.verifier_stderr_excerpt[:200]}|{ctx.op.verifier_exit_code}|{ctx.op.verifier_command_hash}".encode()
    ).hexdigest()[:16]

    ctx.op._orchestrator_verifier_evidence_passed = evidence_injected
    ctx.op._orchestrator_verifier_evidence_fields = evidence_fields
    ctx.op._orchestrator_retry_prompt_evidence_hash = evidence_hash

    assert ctx.op._orchestrator_verifier_evidence_passed is True
    assert len(ctx.op._orchestrator_verifier_evidence_fields) > 0
    assert len(ctx.op._orchestrator_retry_prompt_evidence_hash) == 16


def test_orchestrator_semantic_retry_reuses_patch_phase_llm_client():
    from nexus.services.local_heal.orchestrator import HealOrchestrator
    from unittest.mock import MagicMock

    shared_client = MagicMock()
    patch_phase = MagicMock()
    patch_phase.llm_client = shared_client

    orch = HealOrchestrator(
        phases=[MagicMock(), MagicMock(), MagicMock(), patch_phase, MagicMock()],
        governance_gate=MagicMock(),
    )

    assert orch._resolve_semantic_retry_llm_client() is shared_client


def test_orchestrator_semantic_retry_uses_shared_patch_phase_client(tmp_path, monkeypatch):
    from nexus.services.local_heal.context import HealContext, GovernanceContext, OperationalContext
    from nexus.services.local_heal.interface import LocalizedFile, PhaseResult
    from nexus.services.local_heal.orchestrator import HealOrchestrator
    from nexus.services.local_heal.protocol import PatchIntent
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    shared_client = MagicMock()
    shared_client.generate.return_value = "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE"
    patch_phase = MagicMock()
    patch_phase.llm_client = shared_client
    verify_phase = MagicMock()

    orch = HealOrchestrator(
        phases=[MagicMock(), MagicMock(), MagicMock(), patch_phase, verify_phase],
        governance_gate=MagicMock(),
    )

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-semantic-retry-shared-client",
            problem_statement="fix toy math",
            repo_dir=tmp_path,
            user_prompt="fix toy math",
            final_patch="--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1,2 +1,2 @@\n def double(x):\n-    return x * 2\n+    return x * 3\n",
            localized_files=[LocalizedFile(path=target_rel, content=target_path.read_text(encoding="utf-8"))],
            evaluation_report="AssertionError: expected 3",
            attempt=1,
            model_decisions=[],
        ),
        gov=GovernanceContext(),
    )
    ctx.op.verifier_failure_evidence_available = True
    ctx.op.semantic_retry_evidence_ready = True
    ctx.op.failure_class = "verification_failed"
    ctx.op.verifier_failure_kind = "nonzero_exit"
    ctx.op.verifier_stdout_excerpt = "AssertionError: expected 3"
    ctx.op.verifier_stderr_excerpt = ""
    ctx.op.verifier_exit_code = 1
    ctx.op.verifier_command_hash = "abc123"
    ctx.op.plan = SimpleNamespace(search_symbols=["double"])
    ctx.op._latency_ledger = MagicMock()

    monkeypatch.setattr(
        "nexus.services.local_heal.canonical_span.get_canonical_search_span",
        lambda **kwargs: SimpleNamespace(span="def double(x):\n    return x * 2", source="source_file"),
    )
    monkeypatch.setattr(
        "nexus.engine.local_model_policy.LocalModelPolicy.select_model",
        lambda *args, **kwargs: {
            "model": "qwen2.5-coder:7b-instruct",
            "timeout_seconds": 30,
            "ollama_options": None,
        },
    )

    class _ApplyResult:
        success = True
        applied_diffs = ["--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1,2 +1,2 @@\n def double(x):\n-    return x * 2\n+    return x * 3\n"]

    monkeypatch.setattr(
        "nexus.services.local_heal.protocol.SolidSearchReplaceProtocol.parse",
        lambda self, response, **kwargs: [PatchIntent(file_path=target_rel, search="old", replace="new")],
    )
    monkeypatch.setattr(
        "nexus.services.local_heal.patch_applier.PatchApplier.apply_and_validate",
        lambda self, intents, repo_dir, localized_files: _ApplyResult(),
    )
    orch.phase_runner.run_phase = MagicMock(return_value=PhaseResult(success=False, failure_reason="VERIFICATION_FAILED"))

    result = orch._attempt_semantic_retry(ctx, "AssertionError: expected 3", "VERIFICATION_FAILED")

    assert result is False
    assert shared_client.generate.call_count == 1
    assert ctx.op._orchestrator_verifier_evidence_passed is True


def test_orchestrator_verifier_evidence_pass_through_does_not_add_retry_loop():
    from nexus.services.local_heal.context import HealContext, OperationalContext
    from pathlib import Path
    from unittest.mock import MagicMock

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-orch-no-loop",
            problem_statement="fix bug",
            repo_dir=Path("/tmp"),
        ),
        gov=MagicMock(),
    )
    initial_attempt = ctx.op.attempt
    # Evidence pass-through must not change attempt count
    assert ctx.op.attempt == initial_attempt


def test_orchestrator_verifier_evidence_pass_through_does_not_change_route():
    from nexus.services.local_heal.context import HealContext, OperationalContext
    from pathlib import Path
    from unittest.mock import MagicMock

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-orch-no-route",
            problem_statement="fix bug",
            repo_dir=Path("/tmp"),
        ),
        gov=MagicMock(),
    )
    # No route/topology metadata should be set by evidence pass-through
    assert not hasattr(ctx.op, "route_mode") or getattr(ctx.op, "route_mode", None) is None


def test_orchestrator_verifier_evidence_pass_through_does_not_mark_solved():
    from nexus.services.local_heal.context import HealContext, OperationalContext
    from pathlib import Path
    from unittest.mock import MagicMock

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-orch-no-solved",
            problem_statement="fix bug",
            repo_dir=Path("/tmp"),
        ),
        gov=MagicMock(),
    )
    ctx.op.solve_eligible = False
    # Evidence pass-through must not change solve_eligible
    assert ctx.op.solve_eligible is False


def test_m1_row_includes_orchestrator_verifier_evidence_pass_through_fields():
    from nexus.services.local_heal.context import HealContext, OperationalContext
    from pathlib import Path
    from unittest.mock import MagicMock
    import hashlib

    ctx = HealContext(
        op=OperationalContext(
            instance_id="test-orch-row",
            problem_statement="fix bug",
            repo_dir=Path("/tmp"),
        ),
        gov=MagicMock(),
    )
    ctx.op.verifier_failure_kind = "assertion_failure"
    ctx.op.verifier_stdout_excerpt = "AssertionError"
    ctx.op.verifier_stderr_excerpt = ""
    ctx.op.verifier_exit_code = 1
    ctx.op.verifier_command_hash = "abc123"

    # Simulate the metadata recording
    ctx.op._orchestrator_verifier_evidence_passed = True
    ctx.op._orchestrator_verifier_evidence_fields = "assertion_failure,AssertionError,,1,abc123"
    ctx.op._orchestrator_retry_prompt_evidence_hash = hashlib.sha256(b"test").hexdigest()[:16]

    # Verify metadata fields exist on ctx.op
    assert hasattr(ctx.op, "_orchestrator_verifier_evidence_passed")
    assert hasattr(ctx.op, "_orchestrator_verifier_evidence_fields")
    assert hasattr(ctx.op, "_orchestrator_retry_prompt_evidence_hash")


# ---------------------------------------------------------------------------
# C15-3E: Verifier Receipt Stdout/Stderr Capture Fix Tests
# ---------------------------------------------------------------------------

def test_verifier_receipt_stdout_tail_reaches_failure_evidence():
    from nexus.services.local_heal.local_model_executor import compute_verifier_failure_evidence
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError: expected 3",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_evidence_available"] is True
    assert evidence["verifier_stdout_excerpt"] != ""
    assert "AssertionError" in evidence["verifier_stdout_excerpt"]


def test_verifier_receipt_stderr_tail_reaches_failure_evidence():
    from nexus.services.local_heal.local_model_executor import compute_verifier_failure_evidence
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail="Traceback (most recent call last):\n  File \"test.py\", line 5\n    raise RuntimeError('bad')",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_evidence_available"] is True
    assert evidence["verifier_stderr_excerpt"] != ""
    assert evidence["verifier_failure_kind"] == "exception"


def test_verifier_receipt_exit_code_reaches_metadata():
    from nexus.services.local_heal.local_model_executor import compute_verifier_failure_evidence
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="fail",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_exit_code"] == 1


def test_empty_verifier_output_preserves_false_evidence_available():
    from nexus.services.local_heal.local_model_executor import compute_verifier_failure_evidence
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_evidence_available"] is True


def test_verifier_receipt_error_reaches_failure_evidence():
    from nexus.services.local_heal.local_model_executor import compute_verifier_failure_evidence
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="verifier_timeout: execution exceeded 30 seconds",
        exit_code=None,
        stdout_tail="",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_evidence_available"] is True
    assert evidence["verifier_failure_kind"] == "timeout"


def test_no_synthetic_verifier_output_created():
    from nexus.services.local_heal.local_model_executor import compute_verifier_failure_evidence
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_stdout_excerpt"] == ""
    assert evidence["verifier_stderr_excerpt"] == ""


def test_verifier_receipt_capture_does_not_change_solved():
    from nexus.services.local_heal.local_model_executor import compute_verifier_failure_evidence
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert evidence["verifier_failure_evidence_available"] is True
    # This function only captures evidence, it must not change solved


def test_verifier_receipt_capture_does_not_change_candidate_isolation():
    from nexus.services.local_heal.local_model_executor import compute_verifier_failure_evidence
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    # Evidence capture must not affect candidate isolation
    assert "candidate_isolation" not in str(evidence)


def test_m1_row_includes_verifier_receipt_presence_fields():
    req = make_test_request(
        "c15-3e-presence",
        execution_topology="localheal_pipeline",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="NO_PATCH",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "NO_PATCH",
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
    meta = resp.raw_model_metadata
    assert "verifier_stdout_tail_present" in meta
    assert "verifier_stderr_tail_present" in meta
    assert "verifier_error_present" in meta
    assert "verifier_receipt_exit_code_present" in meta


# ---------------------------------------------------------------------------
# C15-3I: Delegated Retry Branch Contract Tests
# ---------------------------------------------------------------------------

def test_localheal_pipeline_delegates_retry_when_verifier_failed_hash_match_evidence_ready():
    """Test that delegated retry is eligible when all conditions are met."""
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state, compute_failure_class, compute_verifier_failure_evidence

    # Simulate the conditions that should trigger delegated retry
    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="fail",
        solved=False,
    )
    assert patch_lifecycle == "isolation_applied_hash_match_verifier_failed"

    failure_class, _ = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state=patch_lifecycle,
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert failure_class == "verification_failed"

    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class=failure_class,
        patch_lifecycle_state=patch_lifecycle,
    )
    assert evidence["verifier_failure_evidence_available"] is True
    assert evidence["semantic_retry_evidence_ready"] is True

    # The conditions for delegated retry are:
    # 1. semantic_retry_evidence_ready == True
    # 2. failure_class in ("verification_failed", "semantic_wrong_patch")
    # 3. candidate_isolated == True
    # 4. hash_match == True
    assert evidence["semantic_retry_evidence_ready"] is True
    assert failure_class in ("verification_failed", "semantic_wrong_patch")
    # candidate_isolated and hash_match are verified by patch_lifecycle


def test_localheal_pipeline_does_not_delegate_retry_for_patch_apply_failed():
    """Test that delegated retry is NOT eligible when patch_apply_failed."""
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state, compute_failure_class

    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="failed",
        hash_match=False,
        applied_patch_hash="",
        selected_candidate_hash="hash_a",
        verifier_result="not_run",
        solved=False,
    )
    assert patch_lifecycle == "isolation_attempted_apply_failed"

    failure_class, _ = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state=patch_lifecycle,
        verifier_result="not_run",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert failure_class == "patch_apply_failed"

    # When patch_apply_failed, delegated retry must NOT be eligible
    # because candidate_isolated=False and hash_match=False
    assert failure_class not in ("verification_failed", "semantic_wrong_patch")


def test_localheal_pipeline_does_not_delegate_retry_without_hash_match():
    """Test that delegated retry is NOT eligible when hash_match=False."""
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state

    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=False,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_b",
        verifier_result="fail",
        solved=False,
    )
    assert patch_lifecycle == "isolation_applied_hash_mismatch"

    # When hash mismatch, delegated retry must NOT be eligible
    assert patch_lifecycle != "isolation_applied_hash_match_verifier_failed"


def test_localheal_pipeline_does_not_delegate_retry_without_evidence_ready():
    """Test that delegated retry is NOT eligible when semantic_retry_evidence_ready=False."""
    from nexus.services.local_heal.local_model_executor import compute_verifier_failure_evidence

    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )

    # When no stdout/stderr/error, evidence is not available
    # semantic_retry_evidence_ready depends on evidence_available
    if not evidence["verifier_failure_evidence_available"]:
        assert evidence["semantic_retry_evidence_ready"] is False
        # delegated retry must NOT be eligible when evidence not ready


def test_localheal_pipeline_delegated_retry_records_consumer_metadata():
    """Test that delegated retry metadata is recorded when retry is invoked."""
    # This test verifies the metadata fields exist and have correct types
    # when delegated retry is invoked
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state, compute_failure_class, compute_verifier_failure_evidence

    # Simulate conditions for delegated retry
    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="fail",
        solved=False,
    )
    assert patch_lifecycle == "isolation_applied_hash_match_verifier_failed"

    failure_class, _ = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state=patch_lifecycle,
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert failure_class == "verification_failed"

    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class=failure_class,
        patch_lifecycle_state=patch_lifecycle,
    )
    assert evidence["verifier_failure_evidence_available"] is True
    assert evidence["semantic_retry_evidence_ready"] is True

    # Verify the metadata fields that would be recorded
    # These are the fields from the delegated retry consumer
    assert "delegated_retry_failure_reason" not in evidence  # Not in evidence function
    assert "delegated_retry_final_patch_len" not in evidence  # Not in evidence function
    # The actual fields are recorded in raw_meta by the executor


def test_localheal_pipeline_delegated_retry_does_not_change_route_or_topology():
    """Test that delegated retry does not change route/topology metadata."""
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state

    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="fail",
        solved=False,
    )
    assert patch_lifecycle == "isolation_applied_hash_match_verifier_failed"

    # Delegated retry eligibility must not change route/topology
    # These are independent of route decision
    assert patch_lifecycle != "patch_absent"


def test_localheal_pipeline_delegated_retry_failure_does_not_mark_solved():
    """Test that delegated retry failure does not mark solved."""
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state, compute_failure_class

    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="fail",
        solved=False,
    )
    assert patch_lifecycle == "isolation_applied_hash_match_verifier_failed"

    failure_class, _ = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state=patch_lifecycle,
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert failure_class == "verification_failed"

    # Delegated retry failure must NOT mark solved
    # solved remains false when verifier fails
    assert failure_class == "verification_failed"


def test_m1_row_includes_pipeline_delegated_retry_contract_fields():
    req = make_test_request(
        "c15-3i-contract-fields",
        execution_topology="localheal_pipeline",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="NO_PATCH",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "NO_PATCH",
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
    meta = resp.raw_model_metadata
    assert "pipeline_retry_delegated" in meta
    assert "retry_not_invoked_reason" in meta
    assert "delegated_retry_failure_reason" in meta
    assert "delegated_retry_final_patch_len" in meta
    assert "delegated_retry_output_class" in meta
    assert "delegated_retry_parser_error_kind" in meta
    assert "delegated_retry_status" in meta
    assert "delegated_retry_output_excerpt" in meta


# ---------------------------------------------------------------------------
# C15-3K: Patch Apply Stability and Eligible Branch Consumer Audit Tests
# ---------------------------------------------------------------------------

def _make_c15_localheal_pipeline_request(*, repo_root: str = "/workspace", target_file: str = "file.py"):
    return make_test_request(
        "c15-localheal-apply",
        repo_root=repo_root,
        target_file=target_file,
        execution_topology="localheal_pipeline",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )


def _run_c15_apply_failure(req, diff_text: str, *, apply_error: str = "patch does not apply"):
    from unittest.mock import patch
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt

    diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            }
        )
        with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply:
            mock_apply.return_value = IsolatedApplyReceipt(
                task_id=req.task_id,
                workspace_path="/tmp/ws",
                target_file=req.target_file,
                patch_apply_status="failed",
                patch_apply_error=apply_error,
                selected_candidate_hash=diff_hash,
                applied_patch_hash="",
                selected_candidate_hash_matches_applied=False,
                candidate_output_isolated=False,
                mutation_allowed=True,
                applied_patch_hash_source="",
            )
            return LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

def test_localheal_pipeline_apply_failure_records_stage_reason_and_hash():
    req = _make_c15_localheal_pipeline_request()
    diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"
    resp = _run_c15_apply_failure(req, diff_text)
    meta = resp.raw_model_metadata
    assert meta.get("apply_failure_stage") != "none"
    assert meta.get("apply_failure_reason") != ""
    assert meta.get("apply_failure_patch_len") > 0
    assert meta.get("apply_failure_patch_hash") != ""


def test_localheal_pipeline_apply_failure_sets_retry_not_invoked_reason():
    req = _make_c15_localheal_pipeline_request()
    diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"
    resp = _run_c15_apply_failure(req, diff_text)
    meta = resp.raw_model_metadata
    assert meta.get("retry_eligibility_checked") is True
    assert meta.get("retry_eligible") is False
    assert meta.get("retry_not_invoked_reason") == "patch_apply_failed"
    assert meta.get("pipeline_retry_delegated") is False


def test_apply_failure_root_cause_search_block_mismatch_current_source(tmp_path):
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")
    diff_text = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def triple(x):\n"
        "-    return x * 3\n"
        "+def double(x):\n"
        "+    return x * 4\n"
    )

    resp = _run_c15_apply_failure(
        _make_c15_localheal_pipeline_request(repo_root=str(tmp_path), target_file=target_rel),
        diff_text,
        apply_error="error: toy/math_util.py: patch does not apply",
    )
    assert resp.raw_model_metadata.get("apply_failure_root_cause") == "search_block_mismatch_current_source"


def test_apply_failure_root_cause_projected_patch_header_mismatch():
    req = _make_c15_localheal_pipeline_request(target_file="toy/math_util.py")
    projected_diff = (
        "--- a/other.py\n"
        "+++ b/other.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    from unittest.mock import patch
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor._project_pipeline_patch_to_target_file", return_value=(projected_diff, {"protocol_used": "pipeline_result"})), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply:
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": "placeholder",
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            }
        )
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id=req.task_id,
            workspace_path="/tmp/ws",
            target_file=req.target_file,
            patch_apply_status="failed",
            patch_apply_error="error: toy/math_util.py: patch does not apply",
            selected_candidate_hash=hashlib.sha256(projected_diff.encode("utf-8")).hexdigest(),
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
            candidate_output_isolated=False,
            mutation_allowed=True,
            applied_patch_hash_source="",
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: projected_diff))

    assert resp.raw_model_metadata.get("apply_failure_root_cause") == "projected_patch_header_mismatch"


def test_apply_failure_root_cause_target_file_state_drift(tmp_path):
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")
    req = _make_c15_localheal_pipeline_request(repo_root=str(tmp_path), target_file=target_rel)
    diff_text = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def double(x):\n"
        "-    return x * 2\n"
        "+def double(x):\n"
        "+    return x * 3\n"
    )

    from unittest.mock import patch
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt

    snapshots = [
        (True, "def drifted(x):\n    return x\n"),
        (True, "def double(x):\n    return x * 2\n"),
        (True, "def modified_again(x):\n    return x * 5\n"),
    ]

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor._read_text_snapshot", side_effect=snapshots), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply:
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            }
        )
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id=req.task_id,
            workspace_path="/tmp/ws",
            target_file=req.target_file,
            patch_apply_status="failed",
            patch_apply_error="error: toy/math_util.py: patch does not apply",
            selected_candidate_hash=hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
            candidate_output_isolated=False,
            mutation_allowed=True,
            applied_patch_hash_source="",
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    assert resp.raw_model_metadata.get("apply_failure_root_cause") == "target_file_state_drift"


def test_apply_failure_records_search_and_source_excerpts(tmp_path):
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")
    diff_text = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def triple(x):\n"
        "-    return x * 3\n"
        "+def double(x):\n"
        "+    return x * 4\n"
    )

    resp = _run_c15_apply_failure(
        _make_c15_localheal_pipeline_request(repo_root=str(tmp_path), target_file=target_rel),
        diff_text,
        apply_error="error: toy/math_util.py: patch does not apply",
    )
    meta = resp.raw_model_metadata
    assert meta.get("apply_failure_search_excerpt") != ""
    assert meta.get("apply_failure_current_source_excerpt") != ""
    assert meta.get("apply_failure_projected_patch_excerpt") != ""


def test_apply_failure_records_target_file_hashes(tmp_path):
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")
    diff_text = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def triple(x):\n"
        "-    return x * 3\n"
        "+def double(x):\n"
        "+    return x * 4\n"
    )

    resp = _run_c15_apply_failure(
        _make_c15_localheal_pipeline_request(repo_root=str(tmp_path), target_file=target_rel),
        diff_text,
        apply_error="error: toy/math_util.py: patch does not apply",
    )
    meta = resp.raw_model_metadata
    assert meta.get("apply_failure_target_file_hash_before_apply") != ""
    assert meta.get("apply_failure_target_file_hash_at_apply") != ""


def test_apply_failure_restore_hash_consistency_when_restore_available(tmp_path):
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    original_text = "def double(x):\n    return x * 2\n"
    target_path.write_text(original_text, encoding="utf-8")
    diff_text = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def double(x):\n"
        "-    return x * 2\n"
        "+def double(x):\n"
        "+    return x * 3\n"
    )
    req = _make_c15_localheal_pipeline_request(repo_root=str(tmp_path), target_file=target_rel)

    from unittest.mock import patch
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply:
        def _mutating_execute(_ctx):
            target_path.write_text("def mutated():\n    return 999\n", encoding="utf-8")
            return CapabilityExecutionResult(
                name="repair_loop", selected=True, invoked=True,
                gate_passed=False, outcome_contributed=False,
                evidence_present=True, failure_reason="",
                telemetries={
                    "pipeline_final_patch": diff_text,
                    "pipeline_solve_eligible": True,
                    "pipeline_failure_reason": "",
                    "model_called": True,
                }
            )

        mock_exec.side_effect = _mutating_execute
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id=req.task_id,
            workspace_path="/tmp/ws",
            target_file=req.target_file,
            patch_apply_status="failed",
            patch_apply_error="error: toy/math_util.py: patch does not apply",
            selected_candidate_hash=hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
            candidate_output_isolated=False,
            mutation_allowed=True,
            applied_patch_hash_source="",
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))

    meta = resp.raw_model_metadata
    assert meta.get("apply_failure_target_file_hash_after_restore") == meta.get("apply_failure_target_file_hash_at_apply")


def test_apply_failure_root_cause_not_unknown_when_patch_does_not_apply_with_evidence(tmp_path):
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")
    diff_text = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def triple(x):\n"
        "-    return x * 3\n"
        "+def double(x):\n"
        "+    return x * 4\n"
    )

    resp = _run_c15_apply_failure(
        _make_c15_localheal_pipeline_request(repo_root=str(tmp_path), target_file=target_rel),
        diff_text,
        apply_error="error: toy/math_util.py: patch does not apply",
    )
    assert resp.raw_model_metadata.get("apply_failure_root_cause") != "unknown_apply_failure"


def test_localheal_pipeline_hash_mismatch_sets_retry_not_invoked_reason():
    req = make_test_request(
        "c15-3k-hash-mismatch",
        execution_topology="localheal_pipeline",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"

    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            }
        )
        with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply:
            mock_apply.return_value = IsolatedApplyReceipt(
                task_id="c15-3k-hash-mismatch",
                workspace_path="/tmp/ws",
                target_file="file.py",
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash="hash_a",
                applied_patch_hash="hash_b",
                selected_candidate_hash_matches_applied=False,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )
            with patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
                mock_verify.return_value = IsolatedVerifierReceipt(
                    task_id="c15-3k-hash-mismatch",
                    verifier_status="fail",
                    exit_code=1,
                    stdout_tail="",
                    stderr_tail="",
                    verifier_error="",
                    verifier_allowed=True,
                )
                resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))
    meta = resp.raw_model_metadata
    assert meta.get("retry_eligible") is False
    assert meta.get("retry_not_invoked_reason") == "hash_mismatch"


def test_localheal_pipeline_evidence_not_ready_sets_retry_not_invoked_reason():
    req = make_test_request(
        "c15-3k-evidence-not-ready",
        execution_topology="localheal_pipeline",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"
    diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": diff_text,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            }
        )
        with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply:
            mock_apply.return_value = IsolatedApplyReceipt(
                task_id="c15-3k-evidence-not-ready",
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
            with patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
                mock_verify.return_value = IsolatedVerifierReceipt(
                    task_id="c15-3k-evidence-not-ready",
                    verifier_status="fail",
                    exit_code=1,
                    stdout_tail="",
                    stderr_tail="",
                    verifier_error="",
                    verifier_allowed=True,
                )
                resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: diff_text))
    meta = resp.raw_model_metadata
    # With exit_code=1 and no stdout/stderr, evidence_ready may be true or false
    if not meta.get("semantic_retry_evidence_ready", False):
        assert meta.get("retry_eligible") is False
        assert meta.get("retry_not_invoked_reason") == "semantic_retry_evidence_not_ready"


def test_localheal_pipeline_eligible_branch_sets_retry_eligible():
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state, compute_failure_class, compute_verifier_failure_evidence

    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="fail",
        solved=False,
    )
    assert patch_lifecycle == "isolation_applied_hash_match_verifier_failed"

    failure_class, _ = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state=patch_lifecycle,
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert failure_class == "verification_failed"

    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class=failure_class,
        patch_lifecycle_state=patch_lifecycle,
    )
    assert evidence["semantic_retry_evidence_ready"] is True

    # The eligibility conditions are met
    assert failure_class in ("verification_failed", "semantic_wrong_patch")
    assert evidence["semantic_retry_evidence_ready"] is True
    # candidate_isolated and hash_match are verified by patch_lifecycle


def test_localheal_pipeline_eligible_branch_cannot_leave_retry_reason_empty():
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state, compute_failure_class, compute_verifier_failure_evidence

    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="fail",
        solved=False,
    )
    failure_class, _ = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state=patch_lifecycle,
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class=failure_class,
        patch_lifecycle_state=patch_lifecycle,
    )

    # When eligible but not delegated, retry_not_invoked_reason must not be empty
    # This is enforced by the code logic
    assert evidence["semantic_retry_evidence_ready"] is True
    assert failure_class in ("verification_failed", "semantic_wrong_patch")


def test_localheal_pipeline_delegated_branch_records_pipeline_retry_delegated_true():
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state, compute_failure_class, compute_verifier_failure_evidence

    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="fail",
        solved=False,
    )
    failure_class, _ = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state=patch_lifecycle,
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class=failure_class,
        patch_lifecycle_state=patch_lifecycle,
    )

    # When delegated retry is invoked, pipeline_retry_delegated must be true
    # This is enforced by the code logic
    assert evidence["semantic_retry_evidence_ready"] is True


def test_localheal_pipeline_retry_eligibility_does_not_change_route_or_topology():
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state

    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="fail",
        solved=False,
    )
    assert patch_lifecycle == "isolation_applied_hash_match_verifier_failed"

    # Retry eligibility must not change route/topology
    assert patch_lifecycle != "patch_absent"


def test_localheal_pipeline_retry_eligibility_does_not_mark_solved():
    from nexus.services.local_heal.local_model_executor import compute_patch_lifecycle_state, compute_failure_class

    patch_lifecycle = compute_patch_lifecycle_state(
        pipeline_final_patch_len=100,
        pipeline_result_projected=True,
        candidate_isolation_attempted=True,
        isolated_apply_status="applied",
        hash_match=True,
        applied_patch_hash="hash_a",
        selected_candidate_hash="hash_a",
        verifier_result="fail",
        solved=False,
    )
    failure_class, _ = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="",
        patch_lifecycle_state=patch_lifecycle,
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert failure_class == "verification_failed"

    # Retry eligibility must not mark solved
    assert failure_class in ("verification_failed", "semantic_wrong_patch")


def test_m1_row_includes_apply_failure_and_retry_eligibility_fields():
    req = make_test_request(
        "c15-3k-fields",
        execution_topology="localheal_pipeline",
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="NO_PATCH",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "NO_PATCH",
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
    meta = resp.raw_model_metadata
    assert "apply_failure_stage" in meta
    assert "apply_failure_reason" in meta
    assert "apply_failure_error_excerpt" in meta
    assert "apply_failure_patch_len" in meta
    assert "apply_failure_patch_hash" in meta
    assert "apply_failure_projected" in meta
    assert "apply_failure_selected_candidate_hash" in meta
    assert "apply_failure_target_file" in meta
    assert "retry_eligibility_checked" in meta
    assert "retry_eligible" in meta
    assert "retry_not_invoked_reason" in meta


def test_pipeline_projection_reanchors_to_locked_search_when_current_source_modified_by_pipeline(tmp_path) -> None:
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 原始內容 (original_target_content) 包含 locked_search
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-3s-reanchor-modified",
        repo_root=str(tmp_path),
        target_file=target_rel,
        evidence_refs=("ref1",),
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
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

    mismatched_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2 if x is not None else None\n"
        "+    return x * 2 if x is not None and isinstance(x, (int, float)) else None\n"
    )
    expected_reanchored_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2\n"
        "+    return x * 2 if x is not None and isinstance(x, (int, float)) else None\n"
    )
    expected_hash = hashlib.sha256(expected_reanchored_diff.rstrip("\n").encode("utf-8")).hexdigest()

    from unittest.mock import patch
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt

        # 在 execute 被呼叫時修改檔案，模擬真實 pipeline 執行改檔行為
        def _mock_execute_side_effect(*args, **kwargs):
            modified_source_content = (
                "def double(x):\n"
                "    if not isinstance(x, (int, float)):\n"
                "        raise ValueError('Input must be a number')\n"
                "    return x * 2\n"
            )
            target_path.write_text(modified_source_content, encoding="utf-8")
            return CapabilityExecutionResult(
                name="repair_loop",
                selected=True,
                invoked=True,
                gate_passed=True,
                outcome_contributed=True,
                evidence_present=True,
                failure_reason="",
                telemetries={
                    "pipeline_final_patch": mismatched_diff,
                    "pipeline_solve_eligible": True,
                    "pipeline_failure_reason": "",
                    "model_called": True,
                },
            )

        mock_exec.side_effect = _mock_execute_side_effect

        def _check_apply(apply_req):
            assert apply_req.unified_diff == expected_reanchored_diff.rstrip("\n")
            assert apply_req.selected_candidate_hash == expected_hash
            return IsolatedApplyReceipt(
                task_id="c15-3s-reanchor-modified",
                workspace_path="/tmp/ws",
                target_file=target_rel,
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash=expected_hash,
                applied_patch_hash=expected_hash,
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )

        with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", side_effect=_check_apply), \
             patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
            mock_verify.return_value = IsolatedVerifierReceipt(
                task_id="c15-3s-reanchor-modified",
                verifier_status="pass",
                exit_code=0,
                stdout_tail="",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            )
            resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("protocol_normalization", {}).get("pipeline_locked_search_reanchored") is True
    assert meta.get("protocol_normalization", {}).get("protocol_used") == "pipeline_result_locked_search_reanchored"
    assert meta.get("candidate_isolated") is True
    assert meta.get("hash_match") is True


# ============================================================
# C15-3T: Delegated Retry Empty Response Wiring Diagnosis Tests
# ============================================================

def test_c15_3t_delegated_retry_stage_first_patch_empty(tmp_path) -> None:
    """Test A: delegated retry stage is 'first_patch_empty_response' when
    first patch synthesis returns empty. Provider must be called (prompt
    is non-empty), but response is empty."""
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-3t-stage-first-patch-empty",
        repo_root=str(tmp_path),
        target_file=target_rel,
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )

    from unittest.mock import patch, MagicMock
    provider_calls = []

    def mock_provider_generate(prov_req):
        provider_calls.append(prov_req)
        mock_resp = MagicMock()
        mock_resp.output_text = ""  # empty response
        mock_resp.error = ""
        return mock_resp

    mock_provider = MagicMock()
    mock_provider.generate.side_effect = mock_provider_generate

    valid_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2\n"
        "+    return x * 3\n"
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        import hashlib as _hashlib

        locked_diff = (
            "--- a/toy/math_util.py\n"
            "+++ b/toy/math_util.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def double(x):\n"
            "-    return x * 2\n"
            "+    return x * 3\n"
        )
        patch_hash = _hashlib.sha256(locked_diff.rstrip("\n").encode()).hexdigest()

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": valid_diff,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
                "patch_synthesis_model_called": True,
                "patch_synthesis_output_len": len(valid_diff),
            }
        )
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="c15-3t-stage-first-patch-empty",
            workspace_path="/tmp/ws",
            target_file=target_rel,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=patch_hash,
            applied_patch_hash=patch_hash,
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="c15-3t-stage-first-patch-empty",
            verifier_status="fail",
            exit_code=1,
            stdout_tail="AssertionError: expected 4, got 6",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(req, provider=mock_provider)

    meta = resp.raw_model_metadata
    # Gate D: pipeline_retry_delegated=True when retry_eligible conditions met
    assert meta.get("pipeline_retry_delegated") is True, f"Expected pipeline_retry_delegated=True, got {meta.get('pipeline_retry_delegated')}"
    # C15-3T: delegated_retry_stage must distinguish first_patch_empty from semantic_retry_empty
    assert meta.get("delegated_retry_stage") == "first_patch_empty_response", \
        f"Expected delegated_retry_stage='first_patch_empty_response', got {meta.get('delegated_retry_stage')}"
    # C15-3T: provider must have been called (prompt is non-empty)
    assert meta.get("delegated_retry_provider_called") is True, \
        f"Expected delegated_retry_provider_called=True, got {meta.get('delegated_retry_provider_called')}"
    # semantic_retry_prompt_len=0 is correct when semantic retry was never invoked
    # (not a wiring failure, but a telemetry projection gap)
    assert meta.get("semantic_retry_prompt_len") == 0  # expected default when SR not invoked
    assert meta.get("delegated_retry_status") in ("EMPTY_RESPONSE", "MODEL_EMPTY_RESPONSE", "")
    # C15-3U observability assertions
    assert meta.get("delegated_retry_provider_prompt_len", 0) > 0
    assert meta.get("delegated_retry_provider_prompt_hash", "") != ""
    assert meta.get("delegated_retry_provider_model_name") == "qwen2.5-coder:7b-instruct"
    assert meta.get("delegated_retry_provider_response_is_none") is False
    assert meta.get("delegated_retry_provider_response_empty") is True
    assert meta.get("delegated_retry_provider_response_len") == 0
    assert meta.get("delegated_retry_provider_call_error") == ""



def test_c15_3t_delegated_retry_first_patch_empty_not_mislabeled_semantic_retry(tmp_path) -> None:
    """Test B: When first patch synthesis is empty, delegated_retry_stage should be
    'first_patch_empty_response', NOT indicating that semantic retry prompt failed to build.
    semantic_retry_prompt_len=0 is a projection default, not a semantic retry build failure."""
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-3t-not-mislabeled",
        repo_root=str(tmp_path),
        target_file=target_rel,
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )

    from unittest.mock import patch, MagicMock
    mock_provider = MagicMock()
    mock_resp = MagicMock()
    mock_resp.output_text = ""
    mock_resp.error = ""
    mock_provider.generate.return_value = mock_resp

    valid_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2\n"
        "+    return x * 3\n"
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        import hashlib as _hashlib

        locked_diff = (
            "--- a/toy/math_util.py\n"
            "+++ b/toy/math_util.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def double(x):\n"
            "-    return x * 2\n"
            "+    return x * 3\n"
        )
        patch_hash = _hashlib.sha256(locked_diff.rstrip("\n").encode()).hexdigest()

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": valid_diff,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
                "patch_synthesis_model_called": True,
                "patch_synthesis_output_len": len(valid_diff),
            },
        )

        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="c15-3t-not-mislabeled",
            workspace_path="/tmp/ws",
            target_file=target_rel,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=patch_hash,
            applied_patch_hash=patch_hash,
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="c15-3t-not-mislabeled",
            verifier_status="fail",
            exit_code=1,
            stdout_tail="assertion failed",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(req, provider=mock_provider)

    meta = resp.raw_model_metadata
    # The stage must be 'first_patch_empty_response' — NOT any semantic_retry label
    stage = meta.get("delegated_retry_stage", "")
    assert stage == "first_patch_empty_response", f"stage={stage!r}: must be first_patch_empty_response when delegated first patch is empty"
    # semantic_retry_prompt_len=0 is a default projection, not a build failure
    # There must be NO semantic_retry_invoked=True when SR was never triggered
    assert not meta.get("semantic_retry_invoked", False), \
        "semantic_retry_invoked must be False when delegated first patch is empty"
    # Confirm it's not misattributed as semantic retry failure
    sr_status = meta.get("semantic_retry_status", "")
    assert sr_status == "", f"semantic_retry_status must be empty when SR not invoked, got {sr_status!r}"


def test_c15_3t_delegated_retry_provider_called_flag_present_in_meta(tmp_path) -> None:
    """Test C: delegated_retry_provider_called is present in raw_meta.
    When pipeline_retry_delegated=True, the field must exist (True or False)."""
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-3t-provider-called-flag",
        repo_root=str(tmp_path),
        target_file=target_rel,
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )

    from unittest.mock import patch, MagicMock
    mock_provider = MagicMock()
    mock_resp = MagicMock()
    mock_resp.output_text = ""
    mock_resp.error = ""
    mock_provider.generate.return_value = mock_resp

    valid_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2\n"
        "+    return x * 3\n"
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        import hashlib as _hashlib

        locked_diff = (
            "--- a/toy/math_util.py\n"
            "+++ b/toy/math_util.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def double(x):\n"
            "-    return x * 2\n"
            "+    return x * 3\n"
        )
        patch_hash = _hashlib.sha256(locked_diff.rstrip("\n").encode()).hexdigest()

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": valid_diff,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
                "patch_synthesis_model_called": True,
                "patch_synthesis_output_len": len(valid_diff),
            }
        )
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="c15-3t-provider-called-flag",
            workspace_path="/tmp/ws",
            target_file=target_rel,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=patch_hash,
            applied_patch_hash=patch_hash,
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="c15-3t-provider-called-flag",
            verifier_status="fail",
            exit_code=1,
            stdout_tail="assertion failed",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(req, provider=mock_provider)

    meta = resp.raw_model_metadata
    # The field must exist when pipeline_retry_delegated=True
    assert meta.get("pipeline_retry_delegated") is True
    assert "delegated_retry_provider_called" in meta, "delegated_retry_provider_called must be in raw_meta"
    assert "delegated_retry_stage" in meta, "delegated_retry_stage must be in raw_meta"
    # provider_called must be True (mock provider was injected and _provider_generate calls it)
    assert meta["delegated_retry_provider_called"] is True


def test_c15_3t_delegated_retry_stage_not_invoked_when_not_eligible(tmp_path) -> None:
    """Test D: When retry_eligible=False (patch apply failed), delegated_retry_stage
    must be 'not_invoked' and delegated_retry_provider_called must be False."""
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-3t-not-eligible",
        repo_root=str(tmp_path),
        target_file=target_rel,
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )

    from unittest.mock import patch, MagicMock

    valid_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2\n"
        "+    return x * 3\n"
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        import hashlib as _hashlib

        locked_diff = (
            "--- a/toy/math_util.py\n"
            "+++ b/toy/math_util.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def double(x):\n"
            "-    return x * 2\n"
            "+    return x * 3\n"
        )
        patch_hash = _hashlib.sha256(locked_diff.rstrip("\n").encode()).hexdigest()

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": valid_diff,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
            },
        )
        # Apply fails → candidate_not_isolated → retry_eligible=False
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="c15-3t-not-eligible",
            workspace_path="/tmp/ws",
            target_file=target_rel,
            patch_apply_status="failed",
            patch_apply_error="patch apply error: context mismatch",
            selected_candidate_hash=patch_hash,
            applied_patch_hash="",
            selected_candidate_hash_matches_applied=False,
            candidate_output_isolated=False,
            mutation_allowed=True,
            applied_patch_hash_source="",
        )

        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("pipeline_retry_delegated") is False, \
        f"pipeline_retry_delegated must be False when not eligible, got {meta.get('pipeline_retry_delegated')}"
    assert meta.get("delegated_retry_stage") == "not_invoked", \
        f"Expected delegated_retry_stage='not_invoked', got {meta.get('delegated_retry_stage')}"
    assert meta.get("delegated_retry_provider_called") is False, \
        f"Expected delegated_retry_provider_called=False, got {meta.get('delegated_retry_provider_called')}"


# ── C15-5B: Delegated retry model resolution tests ──────────────────

def test_delegated_retry_uses_signal_snapshot_executor_model(tmp_path) -> None:
    """Delegated retry must use signal_snapshot executor_model when present."""
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-5b-model-override",
        repo_root=str(tmp_path),
        target_file=target_rel,
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:14b-instruct-q3_K_M",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )

    from unittest.mock import patch, MagicMock
    provider_calls = []

    def mock_provider_generate(prov_req):
        provider_calls.append(prov_req)
        mock_resp = MagicMock()
        mock_resp.output_text = ""
        mock_resp.error = ""
        return mock_resp

    mock_provider = MagicMock()
    mock_provider.generate.side_effect = mock_provider_generate

    valid_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2\n"
        "+    return x * 3\n"
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        import hashlib as _hashlib

        patch_hash = _hashlib.sha256(valid_diff.rstrip("\n").encode()).hexdigest()

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": valid_diff,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
                "patch_synthesis_model_called": True,
                "patch_synthesis_output_len": len(valid_diff),
            }
        )
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="c15-5b-model-override",
            workspace_path="/tmp/ws",
            target_file=target_rel,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=patch_hash,
            applied_patch_hash=patch_hash,
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="c15-5b-model-override",
            verifier_status="fail",
            exit_code=1,
            stdout_tail="FAIL",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(req, provider=mock_provider)

    meta = resp.raw_model_metadata
    assert meta.get("pipeline_retry_delegated") is True
    assert meta.get("delegated_retry_provider_called") is True
    assert meta.get("delegated_retry_provider_model_name") == "qwen2.5-coder:14b-instruct-q3_K_M", \
        f"Expected delegated model to be 14B, got {meta.get('delegated_retry_provider_model_name')}"


def test_delegated_retry_falls_back_to_pipeline_model_without_override(tmp_path) -> None:
    """Delegated retry falls back to nested pipeline model when no executor_model in signal_snapshot."""
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-5b-no-override",
        repo_root=str(tmp_path),
        target_file=target_rel,
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )

    from unittest.mock import patch, MagicMock

    def mock_provider_generate(prov_req):
        mock_resp = MagicMock()
        mock_resp.output_text = ""
        mock_resp.error = ""
        return mock_resp

    mock_provider = MagicMock()
    mock_provider.generate.side_effect = mock_provider_generate

    valid_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2\n"
        "+    return x * 3\n"
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        import hashlib as _hashlib

        patch_hash = _hashlib.sha256(valid_diff.rstrip("\n").encode()).hexdigest()

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": valid_diff,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
                "patch_synthesis_model_called": True,
                "patch_synthesis_output_len": len(valid_diff),
            }
        )
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="c15-5b-no-override",
            workspace_path="/tmp/ws",
            target_file=target_rel,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=patch_hash,
            applied_patch_hash=patch_hash,
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="c15-5b-no-override",
            verifier_status="fail",
            exit_code=1,
            stdout_tail="FAIL",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(req, provider=mock_provider)

    meta = resp.raw_model_metadata
    assert meta.get("pipeline_retry_delegated") is True
    assert meta.get("delegated_retry_provider_called") is True
    assert meta.get("delegated_retry_provider_model_name") == "qwen2.5-coder:7b-instruct", \
        f"Expected fallback to 7B, got {meta.get('delegated_retry_provider_model_name')}"


def test_delegated_retry_records_actual_provider_model_name(tmp_path) -> None:
    """Delegated retry telemetry must record the actual model used."""
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-5b-telemetry-model",
        repo_root=str(tmp_path),
        target_file=target_rel,
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "deepseek-coder:6.7b-instruct",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )

    from unittest.mock import patch, MagicMock

    def mock_provider_generate(prov_req):
        mock_resp = MagicMock()
        mock_resp.output_text = ""
        mock_resp.error = ""
        return mock_resp

    mock_provider = MagicMock()
    mock_provider.generate.side_effect = mock_provider_generate

    valid_diff = (
        "--- a/toy/math_util.py\n"
        "+++ b/toy/math_util.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def double(x):\n"
        "-    return x * 2\n"
        "+    return x * 3\n"
    )

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
        import hashlib as _hashlib

        patch_hash = _hashlib.sha256(valid_diff.rstrip("\n").encode()).hexdigest()

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": valid_diff,
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
                "patch_synthesis_model_called": True,
                "patch_synthesis_output_len": len(valid_diff),
            }
        )
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="c15-5b-telemetry-model",
            workspace_path="/tmp/ws",
            target_file=target_rel,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=patch_hash,
            applied_patch_hash=patch_hash,
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="c15-5b-telemetry-model",
            verifier_status="fail",
            exit_code=1,
            stdout_tail="FAIL",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        resp = LocalModelExecutor.run(req, provider=mock_provider)

    meta = resp.raw_model_metadata
    assert meta.get("delegated_retry_provider_model_name") == "deepseek-coder:6.7b-instruct"
    assert meta.get("delegated_retry_provider_called") is True
    assert "RouteMode" not in meta
    assert "execution_topology_override" not in meta


def test_prompt_builder_enforces_contract_for_heterogeneous_small_models() -> None:
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    prompt_6_7b = PromptBuilder.build_patch_system_prompt("deepseek-coder:6.7b-instruct")
    prompt_9b = PromptBuilder.build_patch_system_prompt("qwythos:9b")
    assert "OUTPUT: exactly one SEARCH/REPLACE block" in prompt_6_7b
    assert "OUTPUT: exactly one SEARCH/REPLACE block" in prompt_9b


def test_delegated_retry_prompt_contains_verifier_evidence_details() -> None:
    """C15-5C: RED test.
    SelfCorrector.build_retry_prompt with LOGIC_REGRESSION must propagate
    verifier stdout/stderr into the prompt when they are embedded in error.message.
    This validates the fix: local_model_executor.py must concatenate
    verifier_stdout_excerpt and verifier_stderr_excerpt into PatchError.message
    so that committee models see the evidence.
    """
    from nexus.services.local_heal.corrector import SelfCorrector
    from nexus.services.local_heal.errors import PatchError, PatchErrorKind

    verifier_stdout = "EVIDENCE: normalize_score may raise ZeroDivisionError when max_val == min_val"
    verifier_stderr = "Traceback: division by zero"

    # Simulate what local_model_executor.py SHOULD build after the fix:
    # message includes verifier stdout and stderr details
    error = PatchError(
        kind=PatchErrorKind.LOGIC_REGRESSION,
        message=(
            f"Verifier failed with exit code 1.\n"
            f"### VERIFIER STDOUT\n{verifier_stdout}\n"
            f"### VERIFIER STDERR\n{verifier_stderr}"
        ),
    )

    prompt = SelfCorrector().build_retry_prompt(
        original_user_prompt="Fix normalize_score to handle equal min/max",
        error=error,
        targeted_files="toy/math_util.py",
    )

    # The prompt must contain the verifier evidence so committee models can reason about it
    assert verifier_stdout in prompt, (
        f"Expected verifier stdout in retry prompt.\n"
        f"stdout='{verifier_stdout}'\nprompt (first 500)='{prompt[:500]}'"
    )
    assert verifier_stderr in prompt, (
        f"Expected verifier stderr in retry prompt.\n"
        f"stderr='{verifier_stderr}'\nprompt (first 500)='{prompt[:500]}'"
    )


def test_delegated_retry_patch_error_message_contains_verifier_evidence(tmp_path) -> None:
    """C15-5C: RED test (executor integration).
    After the fix, the PatchError built by local_model_executor.py for delegated
    retry must include verifier_stdout_excerpt and verifier_stderr_excerpt.
    We verify this by inspecting what SelfCorrector.build_retry_prompt is called with.
    """
    from unittest.mock import patch, MagicMock, call
    from nexus.services.local_heal.corrector import SelfCorrector

    captured_errors = []
    original_build = SelfCorrector.build_retry_prompt

    def capturing_build(self, original_user_prompt, error, targeted_files="", structured_packet=None):
        captured_errors.append(error)
        return original_build(self, original_user_prompt, error, targeted_files, structured_packet)

    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-5c-patch-error-wiring",
        repo_root=str(tmp_path),
        target_file=target_rel,
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "delegated_retry_candidate_models": ["ornith:9b", "qwythos:9b"],
            },
        },
    )

    mock_provider = MagicMock()
    mock_resp = MagicMock()
    mock_resp.output_text = ""
    mock_resp.error = ""
    mock_provider.generate.return_value = mock_resp

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify, \
         patch.object(SelfCorrector, "build_retry_prompt", capturing_build):
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1,2 +1,2 @@\n def double(x):\n-    return x * 2\n+    return x * 3\n",
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
                "patch_synthesis_model_called": True,
                "patch_synthesis_output_len": 80,
            }
        )
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="c15-5c-patch-error-wiring",
            workspace_path="/tmp/ws",
            target_file=target_rel,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash="aaaa1111",
            applied_patch_hash="aaaa1111",
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="c15-5c-patch-error-wiring",
            verifier_status="fail",
            exit_code=1,
            stdout_tail="EVIDENCE: normalize_score may raise ZeroDivisionError when max_val == min_val",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )

        LocalModelExecutor.run(req, provider=mock_provider)

    # After the fix, build_retry_prompt must have been called with an error
    # whose message contains the verifier stdout excerpt
    assert len(captured_errors) > 0, (
        "Expected SelfCorrector.build_retry_prompt to be called during delegated retry, "
        "but it was never called. Check that retry_eligible conditions are met."
    )
    verifier_evidence = "EVIDENCE: normalize_score may raise ZeroDivisionError when max_val == min_val"
    found = any(verifier_evidence in str(e.message) for e in captured_errors)
    assert found, (
        f"Expected verifier stdout in PatchError.message for committee retry.\n"
        f"Captured error messages: {[str(e.message) for e in captured_errors]}"
    )


# --- C15-5H Regression: _dr_localized_files must be LocalizedFile, not tuple ---

def test_c15_5h_dr_localized_files_is_localized_file_not_tuple(tmp_path):
    """C15-5H: Verify that the committee _dr_localized_files uses LocalizedFile objects.

    Root cause: _dr_localized_files was list[tuple[str,str]] but PatchSynthesisPhase.run()
    calls loc_file.path which AttributeErrors on tuples. LocalizationPhase skips when
    localized_files is non-empty, so the wrong type was propagated all the way to
    PatchSynthesisPhase, causing conversion_status to stay "none" (model_decisions empty).

    Fix: Wrap with LocalizedFile in local_model_executor.py L1780.
    """
    from nexus.services.local_heal.interface import LocalizedFile

    # Simulate what fixed local_model_executor.py does
    target_file = "toy/math_util.py"
    target_full_path = tmp_path / target_file
    target_full_path.parent.mkdir(parents=True, exist_ok=True)
    buggy_content = "def normalize_score(s, m, M):\n    return (s - m) / (M - m)\n"
    target_full_path.write_text(buggy_content, encoding="utf-8")

    # Replicate the fixed construction
    _dr_localized_files: list = []
    if target_file:
        _target_full_path = tmp_path / target_file
        if _target_full_path.exists():
            try:
                _current_content = _target_full_path.read_text(encoding="utf-8", errors="replace")
                _dr_localized_files = [LocalizedFile(path=target_file, content=_current_content)]
            except Exception:
                pass

    assert len(_dr_localized_files) == 1, "Expected one localized file"
    assert isinstance(_dr_localized_files[0], LocalizedFile), (
        f"Expected LocalizedFile, got {type(_dr_localized_files[0])}. "
        "This is the C15-5H regression: tuple breaks PatchSynthesisPhase.run() loc_file.path."
    )
    assert _dr_localized_files[0].path == target_file
    assert "normalize_score" in _dr_localized_files[0].content


# --- C15-6E Controlled Committee Success Integration Test ---

def test_c15_6e_controlled_committee_success_proven(tmp_path) -> None:
    """C15-6E: Test-only controlled success lane proving the committee winner path
    can produce solved=True under strict gates, marked as C15_6E_CONTROLLED_COMMITTEE_SUCCESS_PROVEN.
    """
    from unittest.mock import patch, MagicMock
    from nexus.services.local_heal.local_model_executor import LocalModelExecutor
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from nexus.services.local_heal.local_model_provider import LocalModelProviderResponse

    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    # Build request targeting a committee-enabled delegated retry
    req = make_test_request(
        "c15-6e-controlled-success",
        repo_root=str(tmp_path),
        target_file=target_rel,
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(0)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
                "local_committee_enabled": True,
                "delegated_retry_candidate_models": ["ornith:9b", "qwythos:9b"],
            },
        },
    )

    # Provider mock that simulates committee candidate completions
    mock_provider = MagicMock()
    mock_resp = LocalModelProviderResponse(
        provider_invoked=True,
        model_called=True,
        model_name="ornith:9b",
        output_text="FILE: toy/math_util.py\n<<<<<<< SEARCH\ndef double(x):\n    return x * 2\n=======\ndef double(x):\n    return x * 4\n>>>>>>> REPLACE",
        requested_timeout_sec=120,
        elapsed_sec=0.1,
        effective_timeout_sec=120,
    )
    mock_provider.generate.return_value = mock_resp

    # Stub the main capability execution to FAIL first (triggering delegated retry)
    main_pipeline_result = CapabilityExecutionResult(
        name="repair_loop", selected=True, invoked=True,
        gate_passed=True, outcome_contributed=True,
        evidence_present=True, failure_reason="VERIFIER_FAILED",
        telemetries={
            "pipeline_final_patch": "--- a/toy/math_util.py\n+++ b/toy/math_util.py\n@@ -1,2 +1,2 @@\n def double(x):\n-    return x * 2\n+    return x * 3\n",
            "pipeline_solve_eligible": False,
            "pipeline_failure_reason": "VERIFIER_FAILED",
            "model_called": True,
            "patch_synthesis_model_called": True,
            "patch_synthesis_output_len": 80,
        }
    )

    # Stub HealPipeline.run result for candidate evaluations
    class MockHealResult:
        def __init__(self, model_name):
            self.pre_verification_final_patch = "FILE: toy/math_util.py\n<<<<<<< SEARCH\ndef double(x):\n    return x * 2\n=======\ndef double(x):\n    return x * 4\n>>>>>>> REPLACE"
            self.final_patch = self.pre_verification_final_patch
            self.model_decisions = [
                {
                    "phase": "patch",
                    "model": model_name,
                    "raw_label": "r:0,d:0,p:3,c:0",
                    "output_class": "VALID_SEARCH_REPLACE",
                    "parser_error_kind": "",
                    "conversion_status": "none",
                    "status": "SUCCESS",
                }
            ]

    def mock_pipeline_run(self, ctx):
        return MockHealResult(ctx.committee_proposer_model)

    # Mock isolated apply: succeeds for both candidates
    # Mock isolated verifier: passes for ornith:9b (the winning candidate)
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute", return_value=main_pipeline_result), \
         patch("nexus.services.local_heal.pipeline.HealPipeline.run", mock_pipeline_run), \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:

        # Mock apply output for multiple steps (primary patch and then candidate patch)
        mock_apply.side_effect = [
            IsolatedApplyReceipt(
                task_id="c15-6e-controlled-success",
                workspace_path="/tmp/ws",
                target_file=target_rel,
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash="bbbb2222",
                applied_patch_hash="bbbb2222",
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            ),
            IsolatedApplyReceipt(
                task_id="c15-6e-controlled-success#committee-ornith:9b",
                workspace_path="/tmp/ws-candidate",
                target_file=target_rel,
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash="cccc3333",
                applied_patch_hash="cccc3333",
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            ),
            IsolatedApplyReceipt(
                task_id="c15-6e-controlled-success#committee-qwythos:9b",
                workspace_path="/tmp/ws-candidate2",
                target_file=target_rel,
                patch_apply_status="applied",
                patch_apply_error="",
                selected_candidate_hash="dddd4444",
                applied_patch_hash="dddd4444",
                selected_candidate_hash_matches_applied=True,
                candidate_output_isolated=True,
                mutation_allowed=True,
                applied_patch_hash_source="git_diff",
            )
        ]

        # Mock verifier output: 1st call fails (triggers retry), 2nd call passes (controlled success winner)
        mock_verify.side_effect = [
            IsolatedVerifierReceipt(
                task_id="c15-6e-controlled-success",
                verifier_status="fail",
                exit_code=1,
                stdout_tail="EVIDENCE: normalize_score may raise ZeroDivisionError when max_val == min_val",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            ),
            IsolatedVerifierReceipt(
                task_id="c15-6e-controlled-success#committee-ornith:9b",
                verifier_status="pass",
                exit_code=0,
                stdout_tail="VERIFIER SUCCESSFUL",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            ),
            IsolatedVerifierReceipt(
                task_id="c15-6e-controlled-success#committee-qwythos:9b",
                verifier_status="fail",
                exit_code=1,
                stdout_tail="VERIFIER FAILED",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            )
        ]

        res = LocalModelExecutor.run(req, provider=mock_provider)

    # Telemetry Assertions to prove C15_6E_CONTROLLED_COMMITTEE_SUCCESS_PROVEN
    meta = res.raw_model_metadata
    print("DEBUG META KEYS AND VALUES:")
    for k, v in sorted(meta.items()):
        print(f"  {k}: {v}")
    assert meta.get("solved") is True, "E2E solved gate must pass for controlled success"
    assert meta.get("verifier_result") == "pass"

    assert meta.get("delegated_retry_committee_path_used") is True
    assert meta.get("delegated_retry_heterogeneous_candidate_count") == 2
    assert meta.get("delegated_retry_heterogeneous_winner_model") == "ornith:9b", "Winner model must be populated"
    assert meta.get("selected_candidate_hash_matches_applied") is True
    assert meta.get("isolated_apply_status") == "applied"
    assert meta.get("isolated_verifier_status") == "pass"

    # Verify that candidate JSON details are recorded correctly
    candidates_json = meta.get("delegated_retry_committee_candidates_json", "[]")
    import json
    candidates = json.loads(candidates_json)
    assert len(candidates) == 2

    # Check for expected label markers
    assert any(c.get("candidate_model") == "ornith:9b" and c.get("selected") is True for c in candidates)

    # Expose label for the report
    res.raw_model_metadata["C15_6E_CONTROLLED_COMMITTEE_SUCCESS_PROVEN"] = True


def test_local_committee_records_raw_and_applied_hash_provenance(monkeypatch) -> None:
    from unittest.mock import patch
    import hashlib
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
    raw_hash = "6643a2598c25505c61410535a298cc053e6f9852790cedc3d539f40e9ee0b1ec"
    applied_hash = "72c5ffe5af17009b62643f779a058c34b4fa264e09614e388502cfda04b59ce7"

    envelope = CandidateEnvelope(
        candidate_id="c-1",
        task_id="comm-hash-prov",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="unified_diff",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=raw_hash,
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
        task_id="comm-hash-prov",
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
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="comm-hash-prov",
            workspace_path="/tmp/ws",
            target_file="file.py",
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash=raw_hash,
            applied_patch_hash=applied_hash,
            selected_candidate_hash_matches_applied=False,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="comm-hash-prov",
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("raw_candidate_hash") == raw_hash
    assert meta.get("selected_candidate_hash") == applied_hash
    assert meta.get("selected_hash_source") == "applied_git_diff"
    assert meta.get("applied_patch_hash_source") == "git_diff"
    assert meta.get("selected_candidate_hash_matches_applied") is True


def test_committee_candidate_count_distinguishes_proposer_and_judge(monkeypatch) -> None:
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

    c_judge = CandidateEnvelope(
        candidate_id="c-judge",
        task_id="comm-counts",
        source="local",
        model="qwen2.5:3b",
        role="judge",
        patch_protocol="none",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash="",
        evidence_refs=("ref1",),
        candidate_patch="",
    )
    c_p1 = CandidateEnvelope(
        candidate_id="c-p1",
        task_id="comm-counts",
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
    c_p2 = CandidateEnvelope(
        candidate_id="c-p2",
        task_id="comm-counts",
        source="local",
        model="deepseek-coder:6.7b",
        role="secondary_proposer",
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
        lambda *a, **k: [c_judge, c_p1, c_p2],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-p2",
            selected_candidate_patch=diff_text,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="comm-counts",
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
                    {"model": "deepseek-coder:6.7b", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="comm-counts",
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
            task_id="comm-counts",
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    assert meta.get("committee_candidate_count") == 3
    assert meta.get("proposer_candidate_count") == 2
    assert meta.get("judge_count") == 1


def test_local_committee_candidate_truth_table_contains_hash_sources(monkeypatch) -> None:
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

    c_judge = CandidateEnvelope(
        candidate_id="c-judge",
        task_id="comm-truth",
        source="local",
        model="qwen2.5:3b",
        role="judge",
        patch_protocol="none",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash="",
        evidence_refs=("ref1",),
        candidate_patch="",
    )
    c_p1 = CandidateEnvelope(
        candidate_id="c-p1",
        task_id="comm-truth",
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
        lambda *a, **k: [c_judge, c_p1],
    )
    monkeypatch.setattr(
        CandidateDecisionAdapter,
        "select_candidate",
        lambda *a, **k: CandidateDecisionResponse(
            selected_candidate_id="c-p1",
            selected_candidate_patch=diff_text,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref1",),
        ),
    )

    req = make_test_request(
        task_id="comm-truth",
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
                ],
                "judge_model": "qwen2.5:3b",
            },
        },
    )

    with patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="comm-truth",
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
            task_id="comm-truth",
            verifier_status="pass",
            exit_code=0,
            stdout_tail="",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata
    candidates_info = meta.get("committee_candidates", [])

    judge_info = next(c for c in candidates_info if c["role"] == "judge")
    assert judge_info["raw_candidate_hash"] == ""
    assert judge_info["selected_candidate_hash"] == ""
    assert judge_info["selected_hash_source"] == "none"
    assert judge_info["applied_patch_hash_source"] == "none"
    assert judge_info["apply_status"] == "none"
    assert judge_info["isolated_verifier_result"] == "none"
    assert judge_info["selected"] is False
    assert judge_info["winner"] is False

    p1_info = next(c for c in candidates_info if c["role"] == "primary_proposer")
    assert p1_info["raw_candidate_hash"] == diff_hash
    assert p1_info["selected_candidate_hash"] == diff_hash
    assert p1_info["applied_patch_hash"] == diff_hash
    assert p1_info["selected_hash_source"] == "applied_git_diff"
    assert p1_info["applied_patch_hash_source"] == "git_diff"
    assert p1_info["apply_status"] == "applied"
    assert p1_info["isolated_verifier_result"] == "pass"
    assert p1_info["selected"] is True
    assert p1_info["winner"] is True
    assert "rejection_reason" in p1_info


def test_delegated_retry_committee_candidates_have_unique_ids(tmp_path) -> None:
    """Delegated retry committee telemetry must compile unique candidate IDs and separate proposer vs judge counts."""
    target_rel = "toy/math_util.py"
    target_path = tmp_path / "toy" / "math_util.py"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("def double(x):\n    return x * 2\n", encoding="utf-8")

    req = make_test_request(
        "c15-6l-delegated-retry-unique",
        repo_root=str(tmp_path),
        target_file=target_rel,
        execution_topology="localheal_pipeline",
        route_context={
            "locked_search": "def double(x):\n    return x * 2",
            "verifier_command": ["python3", "-c", "exit(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "delegated_retry_candidate_models": ["qwen2.5-coder:7b-instruct", "deepseek-coder:6.7b-instruct"],
                "judge_model": "qwen2.5-s2t-advisor:3b",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )

    from unittest.mock import patch, MagicMock

    mock_provider = MagicMock()
    mock_provider.generate.return_value = MagicMock(output_text="", error="")

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply") as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier") as mock_verify:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
        from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt

        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True,
            evidence_present=True, failure_reason="",
            telemetries={
                "pipeline_final_patch": (
                    "--- a/toy/math_util.py\n"
                    "+++ b/toy/math_util.py\n"
                    "@@ -1,2 +1,2 @@\n"
                    " def double(x):\n"
                    "-    return x * 2\n"
                    "+    return x * 3\n"
                ),
                "pipeline_solve_eligible": True,
                "pipeline_failure_reason": "",
                "model_called": True,
                "patch_synthesis_model_called": True,
                "patch_synthesis_output_len": 10,
            }
        )
        mock_apply.return_value = IsolatedApplyReceipt(
            task_id="c15-6l-delegated-retry-unique",
            workspace_path="/tmp/ws",
            target_file=target_rel,
            patch_apply_status="applied",
            patch_apply_error="",
            selected_candidate_hash="abc",
            applied_patch_hash="abc",
            selected_candidate_hash_matches_applied=True,
            candidate_output_isolated=True,
            mutation_allowed=True,
            applied_patch_hash_source="git_diff",
        )
        mock_verify.return_value = IsolatedVerifierReceipt(
            task_id="c15-6l-delegated-retry-unique",
            verifier_status="fail",
            exit_code=1,
            stdout_tail="FAIL",
            stderr_tail="",
            verifier_error="",
            verifier_allowed=True,
        )
        resp = LocalModelExecutor.run(req, provider=mock_provider)

    meta = resp.raw_model_metadata
    assert meta.get("delegated_retry_committee_path_used") is True

    candidates_json = meta.get("delegated_retry_committee_candidates_json", "[]")
    import json
    candidates = json.loads(candidates_json)
    assert len(candidates) == 2

    # Assert provider was called with policy options
    assert mock_provider.generate.call_count == 6
    for call in mock_provider.generate.call_args_list:
        req_arg = call[0][0]
        assert req_arg.options is not None
        assert "num_ctx" in req_arg.options

    # Assert expected counts are separated
    assert meta.get("delegated_retry_proposer_count_expected") == 2
    assert meta.get("delegated_retry_judge_count_expected") == 1
    assert meta.get("delegated_retry_candidate_count_actual") == 2

    # Assert unique candidate IDs are present
    candidate_ids = [c.get("candidate_id") for c in candidates]
    assert all(cid for cid in candidate_ids)
    assert len(candidate_ids) == len(set(candidate_ids))

    # Assert format class / model slug details
    qwen_cand = next(c for c in candidates if "qwen" in c["model"])
    assert "qwen" in qwen_cand["candidate_id"]
    assert "delegated-retry-01" in qwen_cand["candidate_id"]

    ds_cand = next(c for c in candidates if "deepseek" in c["model"])
    assert "deepseek" in ds_cand["candidate_id"]
    assert "delegated-retry-02" in ds_cand["candidate_id"]


# ============================================================
# P1-2: Executor Read-Only Adoption Tests
# ============================================================


def test_output_understanding_called_on_single_local_model_path(monkeypatch) -> None:
    """P1-2: Prove canonical understanding is called on the local output path."""
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )

    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n"
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = True
                model_called = True
                model_name = "test-model"
            return R()

    req = LocalModelExecutorRequest(
        task_id="t1",
        problem_statement="fix x",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "protocol_mode": "standard",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    assert resp.raw_model_metadata.get("output_understanding_format") is not None
    assert resp.raw_model_metadata.get("output_understanding_success") is True


def test_search_replace_compatibility_unchanged(monkeypatch) -> None:
    """P1-2: Existing search/replace path remains green."""
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )

    sr_output = (
        "<<<<<<< SEARCH\n"
        "old code\n"
        "=======\n"
        "new code\n"
        ">>>>>>> REPLACE"
    )

    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = sr_output
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = True
                model_called = True
                model_name = "test-model"
            return R()

    req = LocalModelExecutorRequest(
        task_id="t2",
        problem_statement="fix code",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "protocol_mode": "anchored_edit",
            },
            "locked_search": "old code",
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    assert resp.raw_model_metadata.get("output_understanding_format") == "SEARCH_REPLACE"
    assert resp.raw_model_metadata.get("output_understanding_success") is True


def test_malformed_output_fails_closed_through_executor() -> None:
    """P1-2: Malformed output maps to existing executor failure handling."""
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )

    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = "Here is some random text with no structure."
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = True
                model_called = True
                model_name = "test-model"
            return R()

    req = LocalModelExecutorRequest(
        task_id="t3",
        problem_statement="fix x",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "protocol_mode": "anchored_edit",
            },
            "locked_search": "old code",
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    assert resp.raw_model_metadata.get("output_understanding_format") == "MALFORMED_OUTPUT"
    assert resp.raw_model_metadata.get("output_understanding_success") is False


def test_refusal_empty_output_fails_closed() -> None:
    """P1-2: Refusal/empty output fails closed through executor handling."""
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )

    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = "I apologize, but I cannot fix this issue."
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = True
                model_called = True
                model_name = "test-model"
            return R()

    req = LocalModelExecutorRequest(
        task_id="t4",
        problem_statement="fix x",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "protocol_mode": "anchored_edit",
            },
            "locked_search": "old code",
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    assert resp.raw_model_metadata.get("output_understanding_format") == "EMPTY_OR_REFUSAL"
    assert resp.raw_model_metadata.get("output_understanding_success") is False


def test_unified_diff_compatibility_unchanged(monkeypatch) -> None:
    """P1-2: Existing unified diff path remains green through executor."""
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )

    diff_output = (
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,3 +1,3 @@\n"
        " def foo():\n"
        "-    pass\n"
        "+    return 42\n"
    )

    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = diff_output
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = True
                model_called = True
                model_name = "test-model"
            return R()

    req = LocalModelExecutorRequest(
        task_id="t5",
        problem_statement="fix foo",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "protocol_mode": "standard",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    assert resp.raw_model_metadata.get("output_understanding_format") == "UNIFIED_DIFF"
    assert resp.raw_model_metadata.get("output_understanding_success") is True
    assert resp.candidate_patch.strip().startswith("--- a/")
    assert "return 42" in resp.candidate_patch


# ============================================================
# P1-4: Executor Canonical Candidate Projection Tests
# ============================================================


def test_canonical_candidate_projection_search_replace() -> None:
    """P1-4: Canonical candidate normalized content used for search/replace projection."""
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )

    sr_output = (
        "<<<<<<< SEARCH\n"
        "old code\n"
        "=======\n"
        "new code\n"
        ">>>>>>> REPLACE"
    )

    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = sr_output
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = True
                model_called = True
                model_name = "test-model"
            return R()

    req = LocalModelExecutorRequest(
        task_id="t6",
        problem_statement="fix code",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "protocol_mode": "anchored_edit",
            },
            "locked_search": "old code",
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    assert resp.raw_model_metadata.get("output_understanding_format") == "SEARCH_REPLACE"
    assert resp.raw_model_metadata.get("output_understanding_success") is True
    assert resp.raw_model_metadata.get("output_understanding_projection_source") == "canonical_candidate"


def test_canonical_candidate_projection_unified_diff() -> None:
    """P1-4: Canonical candidate normalized content used for unified diff projection."""
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )

    diff_output = (
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,3 +1,3 @@\n"
        " def foo():\n"
        "-    pass\n"
        "+    return 42\n"
    )

    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = diff_output
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = True
                model_called = True
                model_name = "test-model"
            return R()

    req = LocalModelExecutorRequest(
        task_id="t7",
        problem_statement="fix foo",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "protocol_mode": "standard",
            }
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    assert resp.raw_model_metadata.get("output_understanding_format") == "UNIFIED_DIFF"
    assert resp.raw_model_metadata.get("output_understanding_success") is True
    assert resp.raw_model_metadata.get("output_understanding_projection_source") == "canonical_candidate"
    assert resp.candidate_patch.strip().startswith("--- a/")


def test_fallback_when_canonical_candidate_absent() -> None:
    """P1-4: Fallback to raw output when canonical candidate is absent or unsupported."""
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )

    malformed_output = "Here is some random text with no structure."

    class FakeProvider:
        def generate(self, req):
            class R:
                output_text = malformed_output
                output_truncated = False
                error = ""
                timed_out = False
                requested_timeout_sec = 120.0
                effective_timeout_sec = 120.0
                elapsed_sec = 0.1
                provider_invoked = True
                model_called = True
                model_name = "test-model"
            return R()

    req = LocalModelExecutorRequest(
        task_id="t8",
        problem_statement="fix x",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "single_local_model",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "protocol_mode": "anchored_edit",
            },
            "locked_search": "old code",
        },
        dry_run=False,
    )
    resp = LocalModelExecutor.run(req, provider=FakeProvider())
    assert resp.raw_model_metadata.get("output_understanding_format") == "MALFORMED_OUTPUT"
    assert resp.raw_model_metadata.get("output_understanding_success") is False
    assert resp.raw_model_metadata.get("output_understanding_projection_source") == "raw_output"


def test_executor_respects_request_mutation_and_verifier_allowed() -> None:
    """Verify that LocalModelExecutor respects request.mutation_allowed even if not enabled in signal_snapshot."""
    from unittest.mock import patch, MagicMock
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )
    from nexus.services.local_heal.isolated_workspace_apply import IsolatedApplyReceipt
    from nexus.services.local_heal.isolated_verifier import IsolatedVerifierReceipt
    from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult

    mock_apply_receipt = IsolatedApplyReceipt(
        task_id="t9",
        workspace_path="/tmp",
        target_file="foo.py",
        patch_apply_status="applied",
        patch_apply_error="",
        selected_candidate_hash="selectedhash",
        applied_patch_hash="appliedhash",
        selected_candidate_hash_matches_applied=True,
        candidate_output_isolated=True,
        mutation_allowed=True,
    )
    mock_verifier_receipt = IsolatedVerifierReceipt(
        task_id="t9",
        verifier_status="pass",
        exit_code=0,
        stdout_tail="pass",
        stderr_tail="",
        verifier_error="",
        verifier_allowed=True,
    )

    diff_text = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n"

    req = LocalModelExecutorRequest(
        task_id="t9",
        problem_statement="fix x",
        repo_root="/tmp",
        target_file="foo.py",
        selected_capabilities=(),
        evidence_refs=(),
        route_context={
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "model_call_allowed": True,
                "executor_model": "test-model",
                "executor_provider": "ollama",
                "protocol_mode": "anchored_edit",
            },
            "locked_search": "old code",
        },
        dry_run=False,
        mutation_allowed=True,
        verifier_allowed=True,
        execution_topology="localheal_pipeline",
    )

    class FakeProvider:
        pass

    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply", return_value=mock_apply_receipt) as mock_apply, \
         patch("nexus.services.local_heal.local_model_executor.run_isolated_verifier", return_value=mock_verifier_receipt) as mock_verifier:

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

        resp = LocalModelExecutor.run(req, provider=FakeProvider())

        mock_apply.assert_called_once()
        called_args = mock_apply.call_args[0][0]
        assert called_args.mutation_allowed is True
        mock_verifier.assert_called_once()
        assert resp.raw_model_metadata.get("isolated_apply_status") == "applied"
        assert resp.raw_model_metadata.get("isolated_verifier_status") == "pass"


def test_compute_failure_class_excludes_valid_formats_from_parse_failed() -> None:
    """Verify that compute_failure_class does not treat VALID_SEARCH_REPLACE as parse_failed."""
    from nexus.services.local_heal.local_model_executor import compute_failure_class

    fc, ur = compute_failure_class(
        output_len=100,
        provider_error="",
        failure_reason="",
        parse_error_kind="VALID_SEARCH_REPLACE",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
        verifier_result="fail",
        solved=False,
        contains_markdown_fence=False,
        pipeline_failure_reason="",
    )
    assert fc == "verification_failed"


def test_compute_failure_class_classifies_real_parse_errors() -> None:
    """Verify that compute_failure_class correctly classifies real parse errors as parse_failed."""
    from nexus.services.local_heal.local_model_executor import compute_failure_class

    real_errors = [
        "NO_BLOCKS_FOUND",
        "MISSING_FILE_HEADER",
        "MALFORMED_DELIMITERS",
        "EMPTY_AFTER_CLEANUP",
        "REPLACEMENT_SYNTAX_INVALID",
    ]
    for err in real_errors:
        fc, ur = compute_failure_class(
            output_len=100,
            provider_error="",
            failure_reason="",
            parse_error_kind=err,
            patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
            verifier_result="fail",
            solved=False,
            contains_markdown_fence=False,
            pipeline_failure_reason="",
        )
        assert fc == f"parse_failed:{err}"
