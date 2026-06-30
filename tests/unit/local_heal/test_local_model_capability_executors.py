from __future__ import annotations

import hashlib
import pytest

from nexus.services.local_heal.local_model_capability_executors import (
    DDTreeLocalExecutor,
    AutoreasonLocalExecutor,
    ArtifactGateLocalExecutor,
    ClaimGateLocalExecutor,
    DeliveryGateLocalExecutor,
)
from nexus.services.local_heal.local_model_capability_context import LocalModelCapabilityContext
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope


def _make_ctx(selected=("ddtree",), candidates=None):
    return LocalModelCapabilityContext(
        task_id="t1", source_root="/ws", problem_statement="fix bug",
        target_file="a.py", target_symbol="f", selected_capabilities=selected,
        execution_topology="local_committee_only", evidence_refs=("ref1",),
        candidate_pool=candidates or [],
    )


def _make_candidate(cid="c1", role="primary_proposer", patch="patch", score=1.0):
    return CandidateEnvelope(
        candidate_id=cid, task_id="t1", source="local", model="qwen2.5-coder:7b",
        role=role, patch_protocol="anchored_edit", target_file="a.py",
        target_symbol="f", source_anchor_hash="h",
        candidate_patch_hash=hashlib.sha256(patch.encode()).hexdigest(),
        evidence_refs=("ref1",), candidate_patch=patch,
    )


# --- DDTree tests ---

def test_ddtree_no_candidates():
    ctx = _make_ctx(candidates=[])
    r = DDTreeLocalExecutor().execute(ctx)
    assert r.invoked is False
    assert "no_candidates" in r.failure_reason


def test_ddtree_with_candidates():
    c1 = _make_candidate("c1", score=1.0)
    c2 = _make_candidate("c2", score=2.0)
    ctx = _make_ctx(candidates=[c1, c2])
    r = DDTreeLocalExecutor().execute(ctx)
    assert r.invoked is True
    assert r.gate_passed is True
    assert "saved_steps" in r.telemetries


# --- Autoreason tests ---

def test_autoreason_no_candidates():
    ctx = _make_ctx(selected=("autoreason",), candidates=[])
    r = AutoreasonLocalExecutor().execute(ctx)
    assert r.invoked is False
    assert "no_candidates" in r.failure_reason


def test_autoreason_with_candidates():
    c1 = _make_candidate("c1", role="primary_proposer")
    c2 = _make_candidate("c2", role="secondary_proposer")
    ctx = _make_ctx(selected=("autoreason",), candidates=[c1, c2])
    r = AutoreasonLocalExecutor().execute(ctx)
    assert r.invoked is True
    assert r.gate_passed is True
    assert "winner" in r.telemetries


# --- Gate tests ---

def test_artifact_gate_passes_with_evidence():
    ctx = _make_ctx(selected=("artifact_gate",))
    r = ArtifactGateLocalExecutor().execute(ctx)
    assert r.gate_passed is True


def test_artifact_gate_fails_without_evidence():
    ctx = LocalModelCapabilityContext(
        task_id="t1", source_root="/ws", problem_statement="p",
        target_file="a.py", target_symbol="f", selected_capabilities=("artifact_gate",),
        execution_topology="local_committee_only", evidence_refs=(),
    )
    r = ArtifactGateLocalExecutor().execute(ctx)
    assert r.gate_passed is False
    assert "missing" in r.failure_reason


def test_claim_gate_passes_with_evidence_and_anchor():
    ctx = _make_ctx(selected=("claim_gate",))
    ctx.source_anchor["present"] = True
    r = ClaimGateLocalExecutor().execute(ctx)
    assert r.gate_passed is True


def test_claim_gate_fails_without_anchor():
    ctx = _make_ctx(selected=("claim_gate",))
    ctx.source_anchor["present"] = False
    r = ClaimGateLocalExecutor().execute(ctx)
    assert r.gate_passed is False


def test_delivery_gate_always_blocks():
    ctx = _make_ctx(selected=("delivery_gate",))
    r = DeliveryGateLocalExecutor().execute(ctx)
    assert r.gate_passed is False
    assert "blocked" in r.failure_reason
