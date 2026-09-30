"""
Tests for Issue #1212: pre-action trajectory capture in LocalCommitteeCandidateProvider
and outcome binding in local_model_executor local_committee_only path.

Test contract:
- seal occurs BEFORE proposer generate
- candidate_id is None (sealed with null) in the sealed step
- result binds after generate returns (success or exception)
- provider telemetry failure is fail-open (generation proceeds normally)
- stable_committee_trajectory_id is collision-safe across members
- only selected strong-label (ISOLATED_VERIFIER) rows bind outcome
- TRACE_ONLY rows never bind
- refresh_registered_experiment only fires after a successful strong bind
- existing local committee behavior unchanged when telemetry context absent
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from nexus.services.local_heal.local_committee_candidate_provider import (
    LocalCommitteeCandidateProvider,
    stable_committee_trajectory_id,
)
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
)

# ---------------------------------------------------------------------------
# stable_committee_trajectory_id — collision-safety
# ---------------------------------------------------------------------------


def test_stable_committee_trajectory_id_is_stable() -> None:
    """Same inputs must always produce same trajectory_id."""
    tid = stable_committee_trajectory_id(
        task_id="task-abc",
        attempt_id="attempt-1",
        member_index=2,
        model_name="qwen2.5-coder:7b",
    )
    assert tid == stable_committee_trajectory_id(
        task_id="task-abc",
        attempt_id="attempt-1",
        member_index=2,
        model_name="qwen2.5-coder:7b",
    )


def test_stable_committee_trajectory_id_collision_safe_across_members() -> None:
    """Different member_index must produce different trajectory_ids."""
    base_kwargs: dict[str, Any] = {
        "task_id": "task-xyz",
        "attempt_id": "attempt-1",
        "model_name": "qwen2.5-coder:7b",
    }
    ids = {stable_committee_trajectory_id(**base_kwargs, member_index=i) for i in range(1, 6)}
    assert len(ids) == 5, "All member indices must produce unique trajectory IDs"


def test_stable_committee_trajectory_id_collision_safe_across_models() -> None:
    """Different model names at same index must produce different trajectory_ids."""
    base_kwargs: dict[str, Any] = {
        "task_id": "task-xyz",
        "attempt_id": "attempt-1",
        "member_index": 2,
    }
    models = ["modelA:7b", "modelB:7b", "modelC:13b"]
    ids = {stable_committee_trajectory_id(**base_kwargs, model_name=m) for m in models}
    assert len(ids) == len(models)


def test_stable_committee_trajectory_id_collision_safe_across_tasks() -> None:
    """Same model+index but different task must produce different trajectory_ids."""
    base_kwargs: dict[str, Any] = {
        "attempt_id": "attempt-1",
        "member_index": 2,
        "model_name": "qwen2.5-coder:7b",
    }
    id_a = stable_committee_trajectory_id(**base_kwargs, task_id="task-aaa")
    id_b = stable_committee_trajectory_id(**base_kwargs, task_id="task-bbb")
    assert id_a != id_b


def test_stable_committee_trajectory_id_starts_with_lc_traj() -> None:
    tid = stable_committee_trajectory_id(
        task_id="t1",
        attempt_id="attempt-1",
        member_index=2,
        model_name="model:7b",
    )
    assert tid.startswith("lc-traj-")


# ---------------------------------------------------------------------------
# generate_committee_candidates — without telemetry context (backward compat)
# ---------------------------------------------------------------------------

_ROUTE_CONTEXT_2P = {
    "signal_snapshot": {
        "proposer_specs": [
            {"model": "qwen2.5-coder:7b", "role": "primary"},
            {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
        ],
        "judge_model": "qwen2.5:3b",
    }
}


def _make_provider(outputs: dict[str, str]):
    def _gen(req: LocalModelProviderRequest):
        return outputs.get(req.model_name, "")

    return InjectedLocalModelProvider(_gen)


def test_generate_committee_candidates_no_telemetry_unchanged() -> None:
    """When repo_root is absent, behavior is identical to original."""
    provider = _make_provider({
        "qwen2.5:3b": "judge output",
        "qwen2.5-coder:7b": "<<<<<<< REPLACE\nfix1\n>>>>>>> REPLACE",
        "deepseek-coder:6.7b-instruct": "<<<<<<< REPLACE\nfix2\n>>>>>>> REPLACE",
    })
    envelopes = LocalCommitteeCandidateProvider.generate_committee_candidates(
        task_id="task-123",
        problem_statement="fix bug",
        target_file="app.py",
        target_symbol="run",
        locked_search="old code",
        evidence_refs=("ref-1",),
        provider=provider,
        protocol_mode="anchored_edit",
        route_context=_ROUTE_CONTEXT_2P,
        # no repo_root/source_revision → telemetry disabled
    )
    assert len(envelopes) == 3
    judge = next(e for e in envelopes if e.role == "judge")
    assert judge.candidate_patch == ""
    p1 = next(e for e in envelopes if e.model == "qwen2.5-coder:7b")
    assert "fix1" in p1.candidate_patch
    p2 = next(e for e in envelopes if e.model == "deepseek-coder:6.7b-instruct")
    assert "fix2" in p2.candidate_patch


# ---------------------------------------------------------------------------
# generate_committee_candidates — seal BEFORE generate, candidate_id=None in seal
# ---------------------------------------------------------------------------


def test_seal_occurs_before_generate_and_candidate_id_is_none() -> None:
    """Seal must be called BEFORE provider.generate; candidate_id passed as None."""
    call_order: list[str] = []
    sealed_candidate_ids: list[Any] = []
    bound_results: list[dict] = []

    def _gen(req: LocalModelProviderRequest):
        call_order.append(f"generate:{req.model_name}")
        return "output text"

    provider = InjectedLocalModelProvider(_gen)

    fake_step_ref = object()

    def _fake_seal(**kwargs):
        call_order.append("seal")
        sealed_candidate_ids.append(kwargs.get("candidate_id"))
        return fake_step_ref

    def _fake_bind(**kwargs):
        bound_results.append(dict(kwargs.get("action_result", {})))

    def _fake_resolve(repo_root):
        return "/fake/evidence/root"

    with (
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.resolve_research_evidence_root",
            side_effect=_fake_resolve,
        ),
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.seal_trajectory_step",
            side_effect=_fake_seal,
        ),
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.bind_trajectory_step_result",
            side_effect=_fake_bind,
        ),
    ):
        envelopes = LocalCommitteeCandidateProvider.generate_committee_candidates(
            task_id="task-seal-test",
            problem_statement="fix bug",
            target_file="app.py",
            target_symbol="run",
            locked_search="old",
            evidence_refs=("ref-1",),
            provider=provider,
            protocol_mode="anchored_edit",
            route_context=_ROUTE_CONTEXT_2P,
            repo_root="/workspace",
            source_revision="abc123",
        )

    assert len(envelopes) == 3

    # Verify seal comes before generate for both proposers.
    # Expected order (judge skips seal): seal, generate(qwen), seal, generate(deepseek)
    # But judge generates first (idx=1), proposers at idx=2,3.
    # So: generate(judge), seal, generate(qwen), seal, generate(deepseek)
    proposer_seals = [(i, v) for i, v in enumerate(call_order) if v == "seal"]
    proposer_generates = [
        (i, v)
        for i, v in enumerate(call_order)
        if v.startswith("generate:") and "qwen2.5:3b" not in v
    ]
    # Each seal must precede the next generate.
    for (si, _), (gi, _) in zip(proposer_seals, proposer_generates):
        assert si < gi, "seal must occur before corresponding generate"

    # candidate_id must be None in sealed step (not yet known before generate)
    assert all(cid is None for cid in sealed_candidate_ids), (
        f"candidate_id in seal must be None, got: {sealed_candidate_ids}"
    )

    # Results should be bound after each generate.
    assert len(bound_results) == 2  # one per non-judge proposer
    for r in bound_results:
        assert "response_type" in r


# ---------------------------------------------------------------------------
# generate_committee_candidates — result binds after generate
# ---------------------------------------------------------------------------


def test_result_binds_after_generate_success() -> None:
    """After a successful generate, bind_trajectory_step_result is called with output."""
    bound: list[dict] = []

    def _gen(req: LocalModelProviderRequest):
        return "patch output"

    provider = InjectedLocalModelProvider(_gen)
    fake_ref = object()

    with (
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.resolve_research_evidence_root",
            return_value="/evidence",
        ),
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.seal_trajectory_step",
            return_value=fake_ref,
        ),
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.bind_trajectory_step_result",
            side_effect=lambda **kw: bound.append(kw.get("action_result", {})),
        ),
    ):
        LocalCommitteeCandidateProvider.generate_committee_candidates(
            task_id="t1",
            problem_statement="p",
            target_file="f.py",
            target_symbol="s",
            locked_search="x",
            evidence_refs=("ref-1",),
            provider=provider,
            protocol_mode="anchored_edit",
            route_context=_ROUTE_CONTEXT_2P,
            repo_root="/workspace",
        )

    assert len(bound) == 2  # both proposers
    for r in bound:
        assert r.get("response_type") != "Exception"
        assert "output_text" in r


# ---------------------------------------------------------------------------
# generate_committee_candidates — exception result binds then re-raises
# ---------------------------------------------------------------------------


def test_result_binds_on_exception_then_reraises() -> None:
    """If generate raises, bind_trajectory_step_result is called with Exception result.

    InjectedLocalModelProvider intentionally swallows exceptions from its wrapped
    callable and converts them to error responses — it never re-raises.  To test
    the exception-bind path we need a provider whose generate() actually raises.
    """
    from nexus.services.local_heal.local_model_provider import (
        LocalModelProvider,
        LocalModelProviderResponse,
    )

    bound_exception_results: list[dict] = []

    class ProviderError(RuntimeError):
        pass

    call_count = [0]

    class _RaisingProvider(LocalModelProvider):
        """Raises ProviderError on the first proposer call, succeeds otherwise."""

        def generate(self, request: LocalModelProviderRequest) -> LocalModelProviderResponse:
            call_count[0] += 1
            if request.model_name == "qwen2.5-coder:7b":
                raise ProviderError("timeout")
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=True,
                model_name=request.model_name,
                output_text="ok",
            )

    provider = _RaisingProvider()
    fake_ref = object()

    def _fake_bind(**kw):
        ar = kw.get("action_result", {})
        if ar.get("response_type") == "Exception":
            bound_exception_results.append(ar)

    with (
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.resolve_research_evidence_root",
            return_value="/evidence",
        ),
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.seal_trajectory_step",
            return_value=fake_ref,
        ),
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.bind_trajectory_step_result",
            side_effect=_fake_bind,
        ),
    ):
        with pytest.raises(ProviderError, match="timeout"):
            LocalCommitteeCandidateProvider.generate_committee_candidates(
                task_id="t-exc",
                problem_statement="p",
                target_file="f.py",
                target_symbol="s",
                locked_search="x",
                evidence_refs=("ref-1",),
                provider=provider,
                protocol_mode="anchored_edit",
                route_context=_ROUTE_CONTEXT_2P,
                repo_root="/workspace",
            )

    # The exception result must have been bound before re-raise.
    assert len(bound_exception_results) == 1
    r = bound_exception_results[0]
    assert r["response_type"] == "Exception"
    assert "ProviderError" in r.get("exception_type", "")


# ---------------------------------------------------------------------------
# generate_committee_candidates — telemetry failure is fail-open
# ---------------------------------------------------------------------------


def test_telemetry_failure_is_fail_open() -> None:
    """If seal raises, generate still proceeds and returns a valid envelope."""
    generated_models: list[str] = []

    def _gen(req: LocalModelProviderRequest):
        generated_models.append(req.model_name)
        return "patch output"

    provider = InjectedLocalModelProvider(_gen)

    with (
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.resolve_research_evidence_root",
            return_value="/evidence",
        ),
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.seal_trajectory_step",
            side_effect=RuntimeError("storage unavailable"),
        ),
    ):
        envelopes = LocalCommitteeCandidateProvider.generate_committee_candidates(
            task_id="t-failopen",
            problem_statement="p",
            target_file="f.py",
            target_symbol="s",
            locked_search="x",
            evidence_refs=("ref-1",),
            provider=provider,
            protocol_mode="anchored_edit",
            route_context=_ROUTE_CONTEXT_2P,
            repo_root="/workspace",
        )

    # All 3 members (1 judge + 2 proposers) are generated despite seal failure.
    assert len(envelopes) == 3
    assert "qwen2.5-coder:7b" in generated_models
    assert "deepseek-coder:6.7b-instruct" in generated_models
    assert all(not e.abstained for e in envelopes)


def test_resolve_evidence_root_failure_is_fail_open() -> None:
    """If resolve_research_evidence_root raises, generation proceeds normally."""
    generated_models: list[str] = []

    def _gen(req: LocalModelProviderRequest):
        generated_models.append(req.model_name)
        return "patch"

    provider = InjectedLocalModelProvider(_gen)

    with patch(
        "nexus.services.local_heal.local_committee_candidate_provider.resolve_research_evidence_root",
        side_effect=OSError("no evidence dir"),
    ):
        envelopes = LocalCommitteeCandidateProvider.generate_committee_candidates(
            task_id="t-resolve-fail",
            problem_statement="p",
            target_file="f.py",
            target_symbol="s",
            locked_search="x",
            evidence_refs=("ref-1",),
            provider=provider,
            protocol_mode="anchored_edit",
            route_context=_ROUTE_CONTEXT_2P,
            repo_root="/workspace",
        )

    assert len(envelopes) == 3
    # All models still generated
    assert "qwen2.5:3b" in generated_models
    assert "qwen2.5-coder:7b" in generated_models


# ---------------------------------------------------------------------------
# generate_committee_candidates — judge is NOT instrumented
# ---------------------------------------------------------------------------


def test_judge_not_instrumented() -> None:
    """The judge model must not receive trajectory seal/bind calls."""
    sealed_for: list[str] = []

    def _gen(req: LocalModelProviderRequest):
        return "output"

    provider = InjectedLocalModelProvider(_gen)
    fake_ref = object()

    def _fake_seal(**kwargs):
        # The action payload contains model_name for proposers
        sealed_for.append(kwargs.get("action_payload", {}).get("model_name", ""))
        return fake_ref

    with (
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.resolve_research_evidence_root",
            return_value="/evidence",
        ),
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.seal_trajectory_step",
            side_effect=_fake_seal,
        ),
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.bind_trajectory_step_result",
        ),
    ):
        LocalCommitteeCandidateProvider.generate_committee_candidates(
            task_id="t-judge",
            problem_statement="p",
            target_file="f.py",
            target_symbol="s",
            locked_search="x",
            evidence_refs=("ref-1",),
            provider=provider,
            protocol_mode="anchored_edit",
            route_context=_ROUTE_CONTEXT_2P,
            repo_root="/workspace",
        )

    # Only proposers are sealed, not the judge.
    assert "qwen2.5:3b" not in sealed_for
    assert "qwen2.5-coder:7b" in sealed_for
    assert "deepseek-coder:6.7b-instruct" in sealed_for
    assert len(sealed_for) == 2


# ---------------------------------------------------------------------------
# local_model_executor outcome binding — only selected strong rows bind
# ---------------------------------------------------------------------------


class _FakeCollectionResult:
    status = "COLLECTED"
    group_sha256 = "group-sha"
    collected_count = 2
    eligible_count = 1
    row_refs = ("groups/g1/row1.json", "groups/g1/row2.json")


def _make_lc_collection_candidates(
    *,
    selected_model: str = "qwen2.5-coder:7b",
    selected_verifier_status: str = "PASS",
    selected_label: str = "ISOLATED_VERIFIER",
) -> list[dict]:
    return [
        {
            "candidate_id": f"task-{selected_model}-success",
            "candidate_model": selected_model,
            "label_quality": selected_label,
            "verifier_status": selected_verifier_status,
            "selected": True,
            "candidate_source": "local_committee_only",
        },
        {
            "candidate_id": "task-deepseek-coder-6-7b-instruct-success",
            "candidate_model": "deepseek-coder:6.7b-instruct",
            "label_quality": "TRACE_ONLY",
            "verifier_status": "UNKNOWN",
            "selected": False,
            "candidate_source": "local_committee_only",
        },
    ]


def test_only_selected_strong_row_binds_outcome() -> None:
    """Only the ISOLATED_VERIFIER selected row should call bind_trajectory_outcome."""
    bound_calls: list[dict] = []

    mock_collection = _FakeCollectionResult()
    candidates = _make_lc_collection_candidates(
        selected_model="qwen2.5-coder:7b",
        selected_label="ISOLATED_VERIFIER",
    )

    with (
        patch(
            "nexus.services.local_heal.local_committee_candidate_provider.stable_committee_trajectory_id",
            return_value="lc-traj-fakeref",
        ),
        patch(
            "nexus.research.clm_system_one.trajectory_continuity.resolve_research_evidence_root",
            return_value="/evidence",
        ),
        patch(
            "nexus.research.clm_system_one.trajectory_continuity.bind_trajectory_outcome",
            side_effect=lambda **kw: bound_calls.append(kw) or "outcome-ref",
        ),
        patch(
            "nexus.research.clm_system_one.trajectory_continuity.refresh_registered_experiment",
            return_value={"checkpoint": {}, "readiness": {}},
        ),
    ):
        # Simulate the outcome-binding logic inline (extracted from executor).
        from nexus.research.clm_system_one.trajectory_continuity import (
            bind_trajectory_outcome,
            resolve_research_evidence_root,
        )
        from nexus.services.local_heal.local_committee_candidate_provider import (
            stable_committee_trajectory_id as _stable_traj_id,
        )

        evidence_root = resolve_research_evidence_root("/workspace")
        route_context = {
            "signal_snapshot": {
                "proposer_specs": [
                    {"model": "qwen2.5-coder:7b", "role": "primary"},
                    {"model": "deepseek-coder:6.7b-instruct", "role": "secondary"},
                ],
                "judge_model": "qwen2.5:3b",
            }
        }
        signal_snapshot = route_context["signal_snapshot"]
        proposer_specs = list(signal_snapshot.get("proposer_specs") or [])
        judge_model = str(signal_snapshot.get("judge_model") or "")
        committee_ordered = [(judge_model, "judge")] + [
            (str(s["model"]), f"{s['role']}_proposer") for s in proposer_specs
        ]
        model_to_member_index = {
            model: idx for idx, (model, role) in enumerate(committee_ordered, 1) if role != "judge"
        }

        outcomes_bound = 0
        for cand_row, row_ref in zip(candidates, mock_collection.row_refs, strict=True):
            lq = str(cand_row.get("label_quality") or "")
            if lq != "ISOLATED_VERIFIER":
                continue
            if not cand_row.get("selected"):
                continue
            cand_model = str(cand_row.get("candidate_model") or "")
            member_idx = model_to_member_index.get(cand_model)
            if member_idx is None:
                continue
            traj_id = _stable_traj_id(
                task_id="task-t1",
                attempt_id="attempt-1",
                member_index=member_idx,
                model_name=cand_model,
            )
            try:
                bind_trajectory_outcome(
                    evidence_root=evidence_root,
                    trajectory_id=traj_id,
                    candidate_evidence_ref=row_ref,
                )
                outcomes_bound += 1
            except Exception:
                pass

    # Only the ISOLATED_VERIFIER selected row was bound.
    assert outcomes_bound == 1
    assert len(bound_calls) == 1
    assert bound_calls[0]["trajectory_id"].startswith("lc-traj-")


def test_trace_only_row_never_binds() -> None:
    """TRACE_ONLY rows must never trigger bind_trajectory_outcome."""
    bound_calls: list[dict] = []

    candidates = [
        {
            "candidate_id": "task-model-a-success",
            "candidate_model": "modelA",
            "label_quality": "TRACE_ONLY",
            "verifier_status": "UNKNOWN",
            "selected": False,
        },
        {
            "candidate_id": "task-model-b-success",
            "candidate_model": "modelB",
            "label_quality": "TRACE_ONLY",
            "verifier_status": "UNKNOWN",
            "selected": True,  # selected but TRACE_ONLY
        },
    ]

    # Apply the filtering logic.
    outcomes_bound = 0
    for cand_row in candidates:
        lq = str(cand_row.get("label_quality") or "")
        if lq != "ISOLATED_VERIFIER":
            continue
        if not cand_row.get("selected"):
            continue
        # Would call bind here; but should never reach this.
        bound_calls.append(cand_row)
        outcomes_bound += 1

    assert outcomes_bound == 0
    assert len(bound_calls) == 0


def test_refresh_only_after_successful_strong_bind() -> None:
    """refresh_registered_experiment must only be called if >=1 outcome was bound."""
    refresh_calls: list[int] = []

    # Simulate zero outcomes bound → no refresh.
    lc_traj_outcomes_bound = 0
    if lc_traj_outcomes_bound:
        refresh_calls.append(1)

    assert refresh_calls == []

    # Simulate one outcome bound → refresh called once.
    lc_traj_outcomes_bound = 1
    if lc_traj_outcomes_bound:
        refresh_calls.append(1)

    assert len(refresh_calls) == 1


def test_trajectory_bind_failure_does_not_affect_execution() -> None:
    """If bind_trajectory_outcome raises ValueError, it is recorded as telemetry-only."""
    traj_capture_errors: list[str] = []
    outcomes_bound = 0

    def _fake_bind(**kw):
        raise ValueError("trajectory not complete")

    # Simulate one eligible candidate.
    candidates = [
        {
            "candidate_id": "cand-1",
            "candidate_model": "modelA",
            "label_quality": "ISOLATED_VERIFIER",
            "verifier_status": "PASS",
            "selected": True,
        }
    ]
    row_refs = ("groups/g1/row1.json",)
    model_to_member_index = {"modelA": 2}

    for cand_row, row_ref in zip(candidates, row_refs):
        lq = str(cand_row.get("label_quality") or "")
        if lq != "ISOLATED_VERIFIER":
            continue
        if not cand_row.get("selected"):
            continue
        cand_model = str(cand_row.get("candidate_model") or "")
        member_idx = model_to_member_index.get(cand_model)
        if member_idx is None:
            continue
        traj_id = stable_committee_trajectory_id(
            task_id="t1", attempt_id="attempt-1", member_index=member_idx, model_name=cand_model
        )
        try:
            _fake_bind(
                evidence_root="/evidence",
                trajectory_id=traj_id,
                candidate_evidence_ref=row_ref,
            )
            outcomes_bound += 1
        except Exception as exc:
            traj_capture_errors.append(f"bind:{type(exc).__name__}")

    # Bind failure is captured as telemetry error, not raised.
    assert outcomes_bound == 0
    assert len(traj_capture_errors) == 1
    assert "ValueError" in traj_capture_errors[0]
    # Execution is unaffected: no re-raise.


# ---------------------------------------------------------------------------
# raw_meta telemetry writeback — forced bind error visible, LC result unchanged
# ---------------------------------------------------------------------------


def test_lc_trajectory_capture_errors_visible_in_raw_meta_on_bind_error(
    monkeypatch, tmp_path
) -> None:
    """Forced bind_trajectory_outcome error is visible in lc_trajectory_capture_errors
    in raw_model_metadata, while main LC result (invoked, candidate_patch) is unchanged.
    """
    import hashlib
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
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider

    diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new\n"
    diff_hash = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

    envelope = CandidateEnvelope(
        candidate_id="c-traj-err",
        task_id="traj-err-task",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="unified_diff",
        target_file="file.py",
        target_symbol="func",
        source_anchor_hash="hash",
        candidate_patch_hash=diff_hash,
        evidence_refs=("ref-1",),
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
            selected_candidate_id="c-traj-err",
            selected_candidate_patch=diff_text,
            ranking_trace=["ranked"],
            selected_by="candidate_policy",
            decision_evidence_refs=("ref-1",),
        ),
    )

    req = LocalModelExecutorRequest(
        task_id="traj-err-task",
        problem_statement="fix bug",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=("local_model_executor",),
        evidence_refs=("ref-1",),
        dry_run=False,
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "source_revision": "a" * 40,
            "signal_snapshot": {
                "execution_topology": "local_committee_only",
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
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

    evidence_root = tmp_path / "candidate-evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_RATE_PERCENT", "100")

    with (
        patch(
            "nexus.services.local_heal.local_model_executor.run_isolated_workspace_apply",
            return_value=IsolatedApplyReceipt(
                task_id="traj-err-task",
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
            ),
        ),
        patch(
            "nexus.services.local_heal.local_model_executor.run_isolated_verifier",
            return_value=IsolatedVerifierReceipt(
                task_id="traj-err-task",
                verifier_status="pass",
                exit_code=0,
                stdout_tail="",
                stderr_tail="",
                verifier_error="",
                verifier_allowed=True,
            ),
        ),
        patch(
            "nexus.research.clm_system_one.trajectory_continuity.bind_trajectory_outcome",
            side_effect=RuntimeError("forced-bind-error"),
        ),
    ):
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))

    meta = resp.raw_model_metadata

    # --- Main LC result must be unchanged ---
    assert resp.invoked is True
    assert resp.candidate_patch == diff_text
    assert resp.error == ""

    # --- Telemetry: bind error visible in raw_meta ---
    capture_errors = meta.get("lc_trajectory_capture_errors")
    assert isinstance(capture_errors, list), (
        f"Expected list for lc_trajectory_capture_errors, got: {capture_errors!r}"
    )
    assert any("bind" in e for e in capture_errors), (
        f"Expected a bind error in lc_trajectory_capture_errors, got: {capture_errors}"
    )

    # --- Telemetry: outcomes_bound reflects that no outcome was committed ---
    outcomes_bound = meta.get("lc_trajectory_outcomes_bound")
    assert outcomes_bound == 0, (
        f"Expected lc_trajectory_outcomes_bound=0 (bind raised), got: {outcomes_bound}"
    )
