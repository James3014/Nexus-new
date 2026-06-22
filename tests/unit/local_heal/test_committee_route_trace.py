from __future__ import annotations

from types import SimpleNamespace

import hashlib

from nexus.committee.models import CommitteeReceipt
from nexus.services.local_heal.committee_orchestrator import CommitteeOrchestrator
from nexus.services.local_heal.interface import PhaseResult
from nexus.services.local_heal.receipt import build_repair_receipt


class _FixedPhase:
    def __init__(self, *, success: bool = True, failure_reason: str = ""):
        self._result = PhaseResult(success=success, failure_reason=failure_reason)

    def execute(self, ctx):
        return self._result


class _PatchPhase:
    def __init__(self):
        self.calls = 0
        self.invoked_models = []

    def execute(self, ctx):
        self.calls += 1
        model = "qwen2.5-coder:7b-instruct" if self.calls == 1 else "deepseek-coder:6.7b-instruct"
        assert ctx.op.committee_proposer_model == model
        self.invoked_models.append(ctx.op.committee_proposer_model)
        ctx.op.final_patch = f"patch-{self.calls}"
        ctx.op.model_decisions.append(
            {
                "phase": "patch",
                "model": model,
                "raw_label": "r:0,d:0,p:3,c:0",
                "status": "SUCCESS",
            }
        )
        return PhaseResult(success=True)


class _CommitteeControllerStub:
    def __init__(self, task_id: str, domains=None):
        self.task_id = task_id
        self.domains = domains or []
        self.enabled = True
        self._last_proposals = None

    def process_proposals(self, raw_proposals):
        self._last_proposals = list(raw_proposals)
        assert len(raw_proposals) == 2
        assert raw_proposals[0]["model"] == "qwen2.5-coder:7b-instruct"
        assert raw_proposals[1]["model"] == "deepseek-coder:6.7b-instruct"
        return CommitteeReceipt(
            task_id=self.task_id,
            k=len(raw_proposals),
            candidates=[],
            verdicts=[],
            winner_id=f"{self.task_id}-{raw_proposals[1]['model']}-{raw_proposals[1]['attempt']}-abcd",
            confidence=0.93,
            verifier_gap=0.07,
            failure_bucket=None,
            abstain_reason=None,
            total_cost=0.2,
        )


class _FirstCandidateCommitteeControllerStub(_CommitteeControllerStub):
    def process_proposals(self, raw_proposals):
        self._last_proposals = list(raw_proposals)
        assert len(raw_proposals) == 2
        return CommitteeReceipt(
            task_id=self.task_id,
            k=len(raw_proposals),
            candidates=[],
            verdicts=[],
            winner_id=f"{self.task_id}-{raw_proposals[0]['model']}-{raw_proposals[0]['attempt']}-abcd",
            confidence=0.88,
            verifier_gap=0.05,
            failure_bucket=None,
            abstain_reason=None,
            total_cost=0.2,
        )


def _make_ctx():
    return SimpleNamespace(
        op=SimpleNamespace(
            instance_id="C_12481",
            final_patch="",
            model_decisions=[],
            failure_reason="",
            solve_eligible=False,
            runner_completed=False,
        )
    )


def test_committee_orchestrator_records_two_candidate_trace(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _CommitteeControllerStub,
    )

    result = orch.run(ctx)

    assert result is ctx
    trace = ctx.op._committee_trace
    assert trace["schema"] == "nexus.local_heal.committee_trace.v1"
    assert trace["candidate_count"] == 2

    # U3-1: stable candidate_id on each snapshot
    candidates = trace["proposer_candidates"]
    assert [c["candidate_id"] for c in candidates] == [
        "C_12481#candidate-1",
        "C_12481#candidate-2",
    ]
    assert [c["candidate_key"] for c in candidates] == [
        "C_12481#proposer-1",
        "C_12481#proposer-2",
    ]
    assert [c["model"] for c in candidates] == [
        "qwen2.5-coder:7b-instruct",
        "deepseek-coder:6.7b-instruct",
    ]
    # U3-1: selected/applied flags present
    for c in candidates:
        assert "selected" in c
        assert "applied" in c

    # U3-1: judge_selection includes candidate_id fields
    assert trace["judge_selection"]["winner_id"]
    assert trace["judge_selection"]["selected_candidate_id"] == "C_12481#candidate-2"
    assert trace["judge_selection"]["candidate_id_mapping_mode"] == "legacy_winner_id_prefix"
    assert trace["judge_selection"]["selected_model"] == "deepseek-coder:6.7b-instruct"
    assert trace["judge_selection"]["selected_attempt"] == 2
    assert trace["committee_receipt"]["selected_candidate_id"] == "C_12481#candidate-2"
    assert trace["committee_receipt"]["confidence"] == 0.93
    # U3-3B: hash verification fields
    expected_selected_hash = candidates[1]["isolated_patch_sha256"]
    expected_applied_hash = hashlib.sha256(b"patch-2").hexdigest()[:16]
    assert trace["committee_receipt"]["selected_candidate_patch_sha256"] == expected_selected_hash
    assert trace["committee_receipt"]["applied_patch_sha256"] == expected_applied_hash
    assert trace["committee_receipt"]["selected_candidate_apply_hash_match"] is True
    assert ctx.op.final_patch == "patch-2"
    assert ctx.op.solve_eligible is True
    assert orch.patch_phase.invoked_models == [
        "qwen2.5-coder:7b-instruct",
        "deepseek-coder:6.7b-instruct",
    ]
    assert not hasattr(ctx.op, "committee_proposer_model")


def test_committee_trace_is_persisted_into_repair_receipt(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _CommitteeControllerStub,
    )

    orch.run(ctx)
    receipt = build_repair_receipt(ctx)

    committee = receipt["telemetries"]["committee"]
    assert committee["schema"] == "nexus.local_heal.committee_trace.v1"
    assert len(committee["proposer_candidates"]) == 2
    assert committee["proposer_candidates"][0]["candidate_id"] == "C_12481#candidate-1"
    assert committee["proposer_candidates"][1]["candidate_id"] == "C_12481#candidate-2"
    assert committee["judge_selection"]["winner_id"]
    assert committee["judge_selection"]["selected_candidate_id"] == "C_12481#candidate-2"
    assert committee["judge_selection"]["candidate_id_mapping_mode"] == "legacy_winner_id_prefix"
    assert committee["judge_selection"]["selected_model"] == "deepseek-coder:6.7b-instruct"
    assert committee["committee_receipt"]["selected_candidate_id"] == "C_12481#candidate-2"


def test_committee_non_last_selected_candidate_reapplies(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _FirstCandidateCommitteeControllerStub,
    )

    orch.run(ctx)

    assert ctx.op.solve_eligible is True
    assert ctx.op.final_patch == "patch-1"
    assert ctx.op._committee_trace["judge_selection"]["selected_candidate_id"] == "C_12481#candidate-1"
    assert ctx.op._committee_trace["judge_selection"]["candidate_id_mapping_mode"] == "legacy_winner_id_prefix"

    candidates = ctx.op._committee_trace["proposer_candidates"]
    assert candidates[0]["selected"] is True
    assert candidates[0]["applied"] is True
    assert candidates[0]["worktree_applied"] is True
    assert candidates[1]["selected"] is False
    assert candidates[1]["applied"] is False
    assert candidates[1]["worktree_applied"] is False

    receipt = ctx.op._committee_trace["committee_receipt"]
    assert receipt["selected_candidate_apply_supported"] is True
    assert receipt["selected_candidate_applied"] is True
    assert receipt["selected_candidate_reapply_mode"] == "non_last_candidate_reapplied"
    assert receipt["selected_candidate_apply_hash_match"] is True


class _UnrecognizedWinnerCommitteeControllerStub(_CommitteeControllerStub):
    def process_proposals(self, raw_proposals):
        self._last_proposals = list(raw_proposals)
        return CommitteeReceipt(
            task_id=self.task_id,
            k=len(raw_proposals),
            candidates=[],
            verdicts=[],
            winner_id="UNKNOWN_TASK-unknown-model-99-abcdef",
            confidence=0.5,
            verifier_gap=0.1,
            failure_bucket=None,
            abstain_reason=None,
            total_cost=0.1,
        )


def test_committee_route_fails_closed_when_candidate_mapping_missing(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _UnrecognizedWinnerCommitteeControllerStub,
    )

    orch.run(ctx)

    assert ctx.op.solve_eligible is False
    assert ctx.op.final_patch == ""
    assert ctx.op.failure_reason == "COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING"
    assert ctx.op._committee_trace["judge_selection"]["candidate_id_mapping_mode"] == "missing"
    assert ctx.op._committee_trace["judge_selection"]["selected_candidate_id"] == ""
    assert ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_supported"] is False


def test_committee_candidate_ids_are_deterministic(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _CommitteeControllerStub,
    )

    orch.run(ctx)
    candidates = ctx.op._committee_trace["proposer_candidates"]

    # U3-1: candidate_id is deterministic from instance_id + index
    assert candidates[0]["candidate_id"] == "C_12481#candidate-1"
    assert candidates[1]["candidate_id"] == "C_12481#candidate-2"
    # U3-1: candidate_key is preserved as legacy field
    assert candidates[0]["candidate_key"] == "C_12481#proposer-1"
    assert candidates[1]["candidate_key"] == "C_12481#proposer-2"
    # U3-1: selected/applied flags present
    assert candidates[0]["selected"] is False
    assert candidates[0]["applied"] is False
    # U3-3A: candidate 2 is selected by judge (last candidate wins)
    assert candidates[1]["selected"] is True
    assert candidates[1]["applied"] is True


def test_committee_candidates_are_isolated(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _CommitteeControllerStub,
    )

    orch.run(ctx)
    candidates = ctx.op._committee_trace["proposer_candidates"]

    # U3-2: both candidates have isolation_status="stored"
    for c in candidates:
        assert c["isolation_status"] == "stored"
        assert c["isolation_store"] == "committee_trace"

    # U3-3A: non-selected candidate has worktree_applied=false
    assert candidates[0]["worktree_applied"] is False
    # U3-3A: selected candidate has worktree_applied=true
    assert candidates[1]["worktree_applied"] is True

    # U3-2: isolated_patch_sha256 equals patch_sha256
    assert candidates[0]["isolated_patch_sha256"] == candidates[0]["patch_sha256"]
    assert candidates[1]["isolated_patch_sha256"] == candidates[1]["patch_sha256"]

    # U3-2: isolated_patch_length equals patch_length
    assert candidates[0]["isolated_patch_length"] == candidates[0]["patch_length"]
    assert candidates[1]["isolated_patch_length"] == candidates[1]["patch_length"]


def test_committee_non_selected_candidate_remains_unapplied(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _CommitteeControllerStub,
    )

    orch.run(ctx)
    candidates = ctx.op._committee_trace["proposer_candidates"]

    # U3-3A: candidate 1 (non-selected) remains all false
    assert candidates[0]["selected"] is False
    assert candidates[0]["applied"] is False
    assert candidates[0]["worktree_applied"] is False
    # U3-3A: candidate 2 (selected and applied by judge)
    assert candidates[1]["selected"] is True
    assert candidates[1]["applied"] is True
    assert candidates[1]["worktree_applied"] is True


def test_committee_isolation_preserved_in_non_last_reapply(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _FirstCandidateCommitteeControllerStub,
    )

    orch.run(ctx)

    candidates = ctx.op._committee_trace["proposer_candidates"]
    assert len(candidates) == 2

    # U3-3C: non-last selected candidate re-applies successfully
    assert candidates[0]["selected"] is True
    assert candidates[0]["applied"] is True
    assert candidates[0]["worktree_applied"] is True
    assert candidates[1]["selected"] is False
    assert candidates[1]["applied"] is False
    assert candidates[1]["worktree_applied"] is False

    # isolation fields preserved
    for c in candidates:
        assert c["isolation_status"] == "stored"
        assert c["isolated_patch_sha256"] == c["patch_sha256"]
        assert c["isolated_patch_length"] == c["patch_length"]

    assert ctx.op.solve_eligible is True
    assert ctx.op.final_patch == "patch-1"
    assert ctx.op._committee_trace["committee_receipt"]["selected_candidate_reapply_mode"] == "non_last_candidate_reapplied"
    assert ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_hash_match"] is True


def test_committee_isolation_preserved_in_missing_mapping(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _UnrecognizedWinnerCommitteeControllerStub,
    )

    orch.run(ctx)

    candidates = ctx.op._committee_trace["proposer_candidates"]
    assert len(candidates) == 2

    # U3-3A: missing mapping — all selected=false, applied=false, worktree_applied=false
    for c in candidates:
        assert c["selected"] is False
        assert c["applied"] is False
        assert c["worktree_applied"] is False
        assert c["isolation_status"] == "stored"
        assert c["isolated_patch_sha256"] == c["patch_sha256"]
        assert c["isolated_patch_length"] == c["patch_length"]

    assert ctx.op.failure_reason == "COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING"
    assert ctx.op._committee_trace["committee_receipt"]["selected_candidate_applied"] is False
    # U3-3B: no hash fields when mapping missing
    assert ctx.op._committee_trace["committee_receipt"]["selected_candidate_patch_sha256"] == ""
    assert ctx.op._committee_trace["committee_receipt"]["applied_patch_sha256"] == ""
    assert ctx.op._committee_trace["committee_receipt"]["selected_candidate_apply_hash_match"] is False


def test_committee_isolation_fields_persisted_in_receipt(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _CommitteeControllerStub,
    )

    orch.run(ctx)
    receipt = build_repair_receipt(ctx)
    committee = receipt["telemetries"]["committee"]
    candidates = committee["proposer_candidates"]

    # U3-2: isolation fields persist through receipt
    for c in candidates:
        assert c["isolation_status"] == "stored"
        assert c["isolated_patch_sha256"] == c["patch_sha256"]
        assert c["isolated_patch_length"] == c["patch_length"]
        assert c["isolation_store"] == "committee_trace"

    # U3-3A: selected candidate applied state persists
    assert candidates[0]["selected"] is False
    assert candidates[0]["applied"] is False
    assert candidates[0]["worktree_applied"] is False
    assert candidates[1]["selected"] is True
    assert candidates[1]["applied"] is True
    assert candidates[1]["worktree_applied"] is True

    # U3-3A: committee_receipt has selected_candidate_applied
    assert committee["committee_receipt"]["selected_candidate_applied"] is True

    # U3-3B: hash fields persist through receipt
    expected_selected_hash = candidates[1]["isolated_patch_sha256"]
    expected_applied_hash = hashlib.sha256(b"patch-2").hexdigest()[:16]
    assert committee["committee_receipt"]["selected_candidate_patch_sha256"] == expected_selected_hash
    assert committee["committee_receipt"]["applied_patch_sha256"] == expected_applied_hash
    assert committee["committee_receipt"]["selected_candidate_apply_hash_match"] is True


class _HashMismatchPatchPhase:
    def __init__(self):
        self.calls = 0

    def execute(self, ctx):
        self.calls += 1
        model = "qwen2.5-coder:7b-instruct" if self.calls == 1 else "deepseek-coder:6.7b-instruct"
        ctx.op.committee_proposer_model = model
        ctx.op.final_patch = f"patch-{self.calls}"
        ctx.op.model_decisions.append(
            {"phase": "patch", "model": model, "raw_label": "r:0,d:0,p:3,c:0", "status": "SUCCESS"}
        )
        return PhaseResult(success=True)


def test_committee_hash_mismatch_fail_closes(monkeypatch):
    import nexus.services.local_heal.committee_orchestrator as orch_mod

    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _HashMismatchPatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _CommitteeControllerStub,
    )

    _real_hash_fn = orch_mod._compute_patch_hash
    _call_count = {"n": 0}

    def _fake_hash(patch_text):
        _call_count["n"] += 1
        if _call_count["n"] == 3 and patch_text == "patch-2":
            return "mismatched_hash"
        return _real_hash_fn(patch_text)

    monkeypatch.setattr(orch_mod, "_compute_patch_hash", _fake_hash)

    orch.run(ctx)

    assert ctx.op.solve_eligible is False
    assert ctx.op.final_patch == ""
    assert ctx.op.failure_reason == "COMMITTEE_SELECTED_CANDIDATE_APPLY_HASH_MISMATCH"
    receipt = ctx.op._committee_trace["committee_receipt"]
    assert receipt["selected_candidate_apply_hash_match"] is False
    assert receipt["applied_patch_sha256"] == "mismatched_hash"
    assert receipt["selected_candidate_patch_sha256"] == "33df0cf768d9f425"


class _EmptyPatchPhase:
    def __init__(self):
        self.calls = 0

    def execute(self, ctx):
        self.calls += 1
        model = "qwen2.5-coder:7b-instruct" if self.calls == 1 else "deepseek-coder:6.7b-instruct"
        ctx.op.committee_proposer_model = model
        ctx.op.final_patch = ""
        ctx.op.model_decisions.append(
            {"phase": "patch", "model": model, "raw_label": "r:0,d:0,p:0,c:0", "status": "EMPTY"}
        )
        return PhaseResult(success=True)


def test_committee_missing_artifact_fail_closes(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _EmptyPatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _CommitteeControllerStub,
    )

    orch.run(ctx)

    assert ctx.op.solve_eligible is False
    assert ctx.op.final_patch == ""
    assert ctx.op.failure_reason == "COMMITTEE_SELECTED_CANDIDATE_ARTIFACT_MISSING"
    receipt = ctx.op._committee_trace["committee_receipt"]
    assert receipt["selected_candidate_apply_supported"] is False
    assert receipt["selected_candidate_applied"] is False
    assert receipt["selected_candidate_apply_hash_match"] is False
    assert receipt["selected_candidate_reapply_mode"] == "missing_artifact"


def test_committee_hash_mismatch_after_non_last_reapply(monkeypatch):
    import nexus.services.local_heal.committee_orchestrator as orch_mod

    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _FirstCandidateCommitteeControllerStub,
    )

    _real_hash_fn = orch_mod._compute_patch_hash
    _call_count = {"n": 0}

    def _fake_hash(patch_text):
        _call_count["n"] += 1
        if _call_count["n"] == 1 and patch_text == "patch-1":
            return "mismatched_hash"
        return _real_hash_fn(patch_text)

    monkeypatch.setattr(orch_mod, "_compute_patch_hash", _fake_hash)

    orch.run(ctx)

    assert ctx.op.solve_eligible is False
    assert ctx.op.final_patch == ""
    assert ctx.op.failure_reason == "COMMITTEE_SELECTED_CANDIDATE_APPLY_HASH_MISMATCH"
    receipt = ctx.op._committee_trace["committee_receipt"]
    assert receipt["selected_candidate_apply_hash_match"] is False
    assert receipt["selected_candidate_reapply_mode"] == "hash_mismatch"
    assert ctx.op._committee_trace["judge_selection"]["selected_candidate_id"] == "C_12481#candidate-1"


def test_committee_missing_mapping_includes_reapply_mode(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _UnrecognizedWinnerCommitteeControllerStub,
    )

    orch.run(ctx)

    assert ctx.op.failure_reason == "COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING"
    receipt = ctx.op._committee_trace["committee_receipt"]
    assert receipt["selected_candidate_reapply_mode"] == "missing_mapping"
    assert receipt["selected_candidate_apply_supported"] is False
    assert receipt["selected_candidate_apply_hash_match"] is False


def test_committee_receipt_persists_reapply_fields(monkeypatch):
    ctx = _make_ctx()
    orch = CommitteeOrchestrator.__new__(CommitteeOrchestrator)
    orch.k = 2
    orch.repro_phase = _FixedPhase()
    orch.plan_phase = _FixedPhase()
    orch.loc_phase = _FixedPhase()
    orch.patch_phase = _PatchPhase()
    orch.verify_phase = _FixedPhase(success=True)
    monkeypatch.setenv("NEXUS_USE_COMMITTEE", "1")
    monkeypatch.setattr(
        "nexus.services.local_heal.committee_orchestrator.CommitteeControllerV263",
        _CommitteeControllerStub,
    )

    orch.run(ctx)
    receipt = build_repair_receipt(ctx)
    committee = receipt["telemetries"]["committee"]

    assert committee["committee_receipt"]["selected_candidate_reapply_mode"] == "last_candidate_existing_path"
    assert committee["committee_receipt"]["selected_candidate_apply_hash_match"] is True
    assert committee["committee_receipt"]["selected_candidate_patch_sha256"] != ""
    assert committee["committee_receipt"]["applied_patch_sha256"] != ""

    candidates = committee["proposer_candidates"]
    assert candidates[0]["selected"] is False
    assert candidates[0]["applied"] is False
    assert candidates[1]["selected"] is True
    assert candidates[1]["applied"] is True
    assert candidates[1]["worktree_applied"] is True
