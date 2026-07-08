"""P4-R2: Real Winner Path Tests — Candidate → Apply → Verifier → Claim Gate."""
from __future__ import annotations

import hashlib
import os
import tempfile
import pytest
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    CommitteeRoutedToolResult,
    _compute_committee_solved,
    evaluate_and_execute,
)
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


_VALID_PATCH = "def foo():\n    return 42\n"


def _valid_candidate(model: str = "qwen") -> dict:
    return {
        "candidate_patch": _VALID_PATCH,
        "format": "UNIFIED_DIFF",
        "model": model,
        "candidate_id": f"cand-{model}",
    }


def _valid_request(**overrides):
    defaults = {
        "task_id": "r2-test",
        "repo_root": "/tmp",
        "target_file": "foo.py",
        "difficulty": "hard",
        "execution_topology": "cloud_with_local_assist",
        "p3_route_status": "shadow_stage5_escalation_recommended",
        "hard_case_escalation_reason": "retry_failed",
        "source_hash": "abc123",
        "evidence_refs": ("patch.diff", "verification_report.txt"),
        "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        "judge_model": "judge",
    }
    defaults.update(overrides)
    return CommitteeRoutedToolRequest(**defaults)


@pytest.fixture(autouse=True)
def setup_env():
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    yield
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


# ── _compute_committee_solved unit tests ──


def test_solved_true_all_conditions():
    """All four conditions pass → solved=True."""
    assert _compute_committee_solved(
        apply_result={"applied": True, "hash_matches": True},
        verifier_result={"status": "pass"},
        claim_gate_passed=True,
    ) is True


def test_solved_false_apply_failed():
    """Apply failed → solved=False."""
    assert _compute_committee_solved(
        apply_result={"applied": False, "hash_matches": False},
        verifier_result={"status": "pass"},
        claim_gate_passed=True,
    ) is False


def test_solved_false_hash_mismatch():
    """Hash mismatch → solved=False."""
    assert _compute_committee_solved(
        apply_result={"applied": True, "hash_matches": False},
        verifier_result={"status": "pass"},
        claim_gate_passed=True,
    ) is False


def test_solved_false_verifier_failed():
    """Verifier failed → solved=False."""
    assert _compute_committee_solved(
        apply_result={"applied": True, "hash_matches": True},
        verifier_result={"status": "fail"},
        claim_gate_passed=True,
    ) is False


def test_solved_false_claim_gate_failed():
    """Claim gate failed → solved=False."""
    assert _compute_committee_solved(
        apply_result={"applied": True, "hash_matches": True},
        verifier_result={"status": "pass"},
        claim_gate_passed=False,
    ) is False


# ── E2E winner path tests ──


def test_valid_candidate_winner_path_success():
    """P4-R2: Valid candidate → winner found → apply/verifier/claim all pass → solved."""
    def producer(req):
        return [_valid_candidate()]

    with tempfile.TemporaryDirectory() as tmpdir:
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        request = _valid_request(repo_root=tmpdir)
        result = evaluate_and_execute(request, candidate_producer=producer)
        assert result.invoked is True
        assert result.winner_found is True
        assert result.selected_candidate_apply_status == "applied"
        assert result.selected_candidate_verifier_status == "pass"
        assert result.receipt_fragment.get("p4_selected_candidate_hash_matches_applied") is True
        assert result.receipt_fragment.get("p4_committee_claim_gate_passed") is True
        assert result.selected_candidate_source_model == "qwen"
        assert result.candidate_count >= 1
        assert result.canonical_candidate_count >= 1
        assert result.raw_candidate_count >= 1


def test_apply_fail_no_solved():
    """P4-R2: Apply fails → solved_by_committee=False."""
    def producer(req):
        return [_valid_candidate()]

    request = _valid_request(mutation_allowed=False)
    result = evaluate_and_execute(request, candidate_producer=producer)
    assert result.winner_found is True
    assert result.selected_candidate_apply_status == "failed"
    assert result.solved_by_committee is False


def test_verifier_fail_no_solved():
    """P4-R2: Verifier fails → solved_by_committee=False."""
    def producer(req):
        return [{"candidate_patch": "def bad(:", "format": "UNIFIED_DIFF", "model": "qwen", "candidate_id": "cand-bad"}]

    with tempfile.TemporaryDirectory() as tmpdir:
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        request = _valid_request(repo_root=tmpdir)
        result = evaluate_and_execute(request, candidate_producer=producer)
        assert result.winner_found is True
        assert result.selected_candidate_apply_status == "applied"
        assert result.selected_candidate_verifier_status == "fail"
        assert result.solved_by_committee is False


def test_hash_mismatch_no_solved():
    """P4-R2: Hash mismatch → solved_by_committee=False.

    Use SEARCH/REPLACE format so normalized_patch differs from raw_output.
    raw_output_hash (sha256 of full SEARCH/REPLACE block) won't match
    applied hash (sha256 of extracted replacement content).
    """
    def producer(req):
        return [{
            "candidate_patch": "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE",
            "format": "SEARCH_REPLACE",
            "model": "qwen",
            "candidate_id": "cand-hash",
        }]

    with tempfile.TemporaryDirectory() as tmpdir:
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        request = _valid_request(repo_root=tmpdir)
        result = evaluate_and_execute(request, candidate_producer=producer)
        assert result.winner_found is True
        # normalized_patch is "new" but raw_output_hash is sha256 of full block
        assert result.solved_by_committee is False


def test_claim_gate_fail_no_solved():
    """P4-R2: Claim gate fails (no source_hash) → solved_by_committee=False."""
    def producer(req):
        return [_valid_candidate()]

    with tempfile.TemporaryDirectory() as tmpdir:
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        request = _valid_request(repo_root=tmpdir, source_hash="")
        result = evaluate_and_execute(request, candidate_producer=producer)
        assert result.winner_found is True
        assert result.receipt_fragment.get("p4_committee_claim_gate_passed") is False
        assert result.solved_by_committee is False


def test_winner_source_model_from_raw_candidate():
    """P4-R2: Model name correctly tracked from raw candidate."""
    def producer(req):
        return [_valid_candidate(model="deepseek-coder")]

    with tempfile.TemporaryDirectory() as tmpdir:
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        request = _valid_request(repo_root=tmpdir)
        result = evaluate_and_execute(request, candidate_producer=producer)
        assert result.selected_candidate_source_model == "deepseek-coder"


def test_mutation_not_allowed_fail_closed():
    """P4-R2: mutation_allowed=False → apply blocked → solved=False."""
    def producer(req):
        return [_valid_candidate()]

    with tempfile.TemporaryDirectory() as tmpdir:
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        request = _valid_request(repo_root=tmpdir, mutation_allowed=False)
        result = evaluate_and_execute(request, candidate_producer=producer)
        assert result.winner_found is True
        assert result.selected_candidate_apply_status == "failed"
        assert result.solved_by_committee is False


def test_selection_strategy_recorded():
    """P4-R2: Selection strategy is noted (first_valid_no_diversity)."""
    def producer(req):
        return [_valid_candidate(model="a"), _valid_candidate(model="b")]

    with tempfile.TemporaryDirectory() as tmpdir:
        foo_path = os.path.join(tmpdir, "foo.py")
        with open(foo_path, "w") as f:
            f.write("x = 1\n")

        request = _valid_request(repo_root=tmpdir)
        result = evaluate_and_execute(request, candidate_producer=producer)
        assert result.winner_found is True
        # First candidate selected (model "a")
        assert result.selected_candidate_source_model == "a"
