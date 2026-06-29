from __future__ import annotations

import pytest
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope


def test_candidate_envelope_valid_primary_proposer() -> None:
    env = CandidateEnvelope(
        candidate_id="cand-1",
        task_id="task-1",
        source="local",
        model="qwen2.5-coder:7b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="app.py",
        target_symbol="run",
        source_anchor_hash="hash-1",
        candidate_patch_hash="hash-2",
        evidence_refs=("ref-1",),
        candidate_patch="print('hello')",
    )
    assert env.candidate_id == "cand-1"
    assert env.role == "primary_proposer"
    assert env.candidate_patch == "print('hello')"


def test_candidate_envelope_valid_judge_no_patch() -> None:
    env = CandidateEnvelope(
        candidate_id="cand-2",
        task_id="task-1",
        source="local",
        model="qwen2.5:3b",
        role="judge",
        patch_protocol="none",
        target_file="app.py",
        target_symbol="run",
        source_anchor_hash="hash-1",
        candidate_patch_hash="hash-empty",
        evidence_refs=("ref-1",),
        candidate_patch="",
    )
    assert env.role == "judge"
    assert env.candidate_patch == ""


def test_candidate_envelope_judge_with_patch_rejected() -> None:
    with pytest.raises(ValueError, match="cannot generate repair patches"):
        CandidateEnvelope(
            candidate_id="cand-3",
            task_id="task-1",
            source="local",
            model="qwen2.5:3b",
            role="judge",
            patch_protocol="anchored_edit",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-2",
            evidence_refs=("ref-1",),
            candidate_patch="print('bad judge')",
        )


def test_candidate_envelope_missing_evidence_refs_rejected() -> None:
    with pytest.raises(ValueError, match="evidence_refs must not be empty"):
        CandidateEnvelope(
            candidate_id="cand-4",
            task_id="task-1",
            source="local",
            model="qwen2.5-coder:7b",
            role="primary_proposer",
            patch_protocol="anchored_edit",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-2",
            evidence_refs=(),
            candidate_patch="print('hello')",
        )


def test_candidate_envelope_invalid_source_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid source"):
        CandidateEnvelope(
            candidate_id="cand-5",
            task_id="task-1",
            source="invalid_source",
            model="qwen",
            role="primary_proposer",
            patch_protocol="anchored_edit",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-2",
            evidence_refs=("ref-1",),
            candidate_patch="print('hello')",
        )


def test_candidate_envelope_invalid_role_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid role"):
        CandidateEnvelope(
            candidate_id="cand-6",
            task_id="task-1",
            source="local",
            model="qwen",
            role="invalid_role",
            patch_protocol="anchored_edit",
            target_file="app.py",
            target_symbol="run",
            source_anchor_hash="hash-1",
            candidate_patch_hash="hash-2",
            evidence_refs=("ref-1",),
            candidate_patch="print('hello')",
        )
