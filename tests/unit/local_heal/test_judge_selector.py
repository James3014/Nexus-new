from __future__ import annotations

import hashlib
import pytest

from nexus.services.local_heal.judge_selector import JudgeSelector, JudgeSelectionReceipt
from nexus.services.local_heal.heterogeneous_candidate_provider import HeterogeneousCandidate


def _make_candidate(cid, role):
    return HeterogeneousCandidate(
        candidate_id=cid, model_name="test-model:7b", role=role,
        candidate_patch_hash=hashlib.sha256(b"patch").hexdigest(),
        source_anchor_hash="h", evidence_refs=("ref1",),
    )


def test_primary_preferred():
    selector = JudgeSelector(judge_model="test-judge:3b")
    candidates = [
        _make_candidate("c1", "secondary_proposer"),
        _make_candidate("c2", "primary_proposer"),
    ]
    receipt = selector.select(candidates)
    assert receipt.selected_candidate_id == "c2"
    assert receipt.judge_invoked is True
    assert receipt.judge_cannot_verify is True


def test_empty_candidates():
    selector = JudgeSelector(judge_model="test-judge:3b")
    receipt = selector.select([])
    assert receipt.selected_candidate_id == ""
    assert receipt.judge_invoked is False


def test_single_candidate():
    selector = JudgeSelector(judge_model="test-judge:3b")
    receipt = selector.select([_make_candidate("c1", "primary_proposer")])
    assert receipt.selected_candidate_id == "c1"


def test_judge_model_required_fail_closed():
    with pytest.raises(ValueError, match="judge_model is required"):
        JudgeSelector()
