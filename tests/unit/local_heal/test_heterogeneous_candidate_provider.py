from __future__ import annotations

import hashlib
import pytest

from nexus.services.local_heal.heterogeneous_candidate_provider import (
    HeterogeneousCandidateProvider,
    HeterogeneousCandidate,
)


def test_primary_always_runs():
    provider = HeterogeneousCandidateProvider(primary_model="test-model:7b")
    candidates = provider.generate_candidates(
        task_id="t1", problem_statement="fix", target_file="a.py",
        target_symbol="f", locked_search="def f(): pass",
        evidence_refs=("ref1",),
    )
    assert len(candidates) == 1
    assert candidates[0].role == "primary_proposer"
    assert candidates[0].model_name == "test-model:7b"


def test_secondary_only_on_disagreement():
    provider = HeterogeneousCandidateProvider(
        primary_model="test-model:7b", secondary_model="test-secondary:6b",
    )
    candidates = provider.generate_candidates(
        task_id="t2", problem_statement="fix", target_file="a.py",
        target_symbol="f", locked_search="def f(): pass",
        evidence_refs=("ref1",), disagreement_detected=True,
    )
    assert len(candidates) == 2
    roles = [c.role for c in candidates]
    assert "primary_proposer" in roles
    assert "secondary_proposer" in roles


def test_secondary_only_on_high_uncertainty():
    provider = HeterogeneousCandidateProvider(
        primary_model="test-model:7b", secondary_model="test-secondary:6b",
    )
    candidates = provider.generate_candidates(
        task_id="t3", problem_statement="fix", target_file="a.py",
        target_symbol="f", locked_search="def f(): pass",
        evidence_refs=("ref1",), high_uncertainty=True,
    )
    assert len(candidates) == 2
    assert candidates[1].trigger_reason == "high_uncertainty"


def test_no_secondary_without_trigger():
    provider = HeterogeneousCandidateProvider(primary_model="test-model:7b")
    candidates = provider.generate_candidates(
        task_id="t4", problem_statement="fix", target_file="a.py",
        target_symbol="f", locked_search="def f(): pass",
        evidence_refs=("ref1",),
    )
    assert len(candidates) == 1


def test_bucket_recorded():
    provider = HeterogeneousCandidateProvider(
        primary_model="test-model:7b", secondary_model="test-secondary:6b",
    )
    candidates = provider.generate_candidates(
        task_id="t5", problem_statement="fix", target_file="a.py",
        target_symbol="f", locked_search="def f(): pass",
        evidence_refs=("ref1",), disagreement_detected=True,
    )
    assert candidates[0].bucket == "default"
    assert candidates[1].bucket == "disagreement"


def test_primary_model_required_fail_closed():
    with pytest.raises(ValueError, match="primary_model is required"):
        HeterogeneousCandidateProvider()
