"""
H8-9 First Solve Harness Fake Candidate Tests

Gate: H8 first solve path with deterministic fake candidate.
"""

from __future__ import annotations

import pytest

from nexus.services.local_heal.first_solve_harness import (
    SolveAttemptReceipt,
    run_first_solve_harness,
)


class TestH89HarnessInput:
    def test_h8_9_first_solve_harness_accepts_problem_and_evidence_refs(self):
        r = run_first_solve_harness(
            task_id="t1",
            problem_statement="test problem",
            evidence_refs=("e1",),
            candidate_id="c1",
            candidate_patch_or_output="fake output",
            selected_candidate_hash="sha256:c1",
        )
        assert r.task_id == "t1"
        assert r.candidate_id == "c1"

    def test_h8_9_first_solve_harness_requires_evidence_refs(self):
        with pytest.raises(ValueError, match="evidence_refs"):
            run_first_solve_harness(
                task_id="t1",
                problem_statement="x",
                evidence_refs=(),
                candidate_id="c1",
                candidate_patch_or_output="x",
                selected_candidate_hash="sha256:c1",
            )

    def test_h8_9_first_solve_harness_requires_candidate_id_and_hash(self):
        with pytest.raises(ValueError, match="candidate_id"):
            run_first_solve_harness(
                task_id="t1",
                problem_statement="x",
                evidence_refs=("e1",),
                candidate_id="",
                candidate_patch_or_output="x",
                selected_candidate_hash="sha256:c1",
            )


class TestH89HarnessSafety:
    def test_h8_9_first_solve_harness_uses_fake_candidate_only(self):
        r = run_first_solve_harness(
            task_id="t1",
            problem_statement="x",
            evidence_refs=("e1",),
            candidate_id="c1",
            candidate_patch_or_output="fake",
            selected_candidate_hash="sha256:c1",
        )
        assert r.fake_candidate_used is True
        assert r.real_model_used is False

    def test_h8_9_first_solve_harness_does_not_call_model(self):
        r = run_first_solve_harness(
            task_id="t1",
            problem_statement="x",
            evidence_refs=("e1",),
            candidate_id="c1",
            candidate_patch_or_output="fake",
            selected_candidate_hash="sha256:c1",
        )
        assert r.local_model_called is False
        assert r.model_called is False

    def test_h8_9_first_solve_harness_does_not_load_model(self):
        r = run_first_solve_harness(
            task_id="t1",
            problem_statement="x",
            evidence_refs=("e1",),
            candidate_id="c1",
            candidate_patch_or_output="fake",
            selected_candidate_hash="sha256:c1",
        )
        assert r.local_model_loaded is False
        assert r.model_loaded is False

    def test_h8_9_first_solve_harness_does_not_apply_patch(self):
        r = run_first_solve_harness(
            task_id="t1",
            problem_statement="x",
            evidence_refs=("e1",),
            candidate_id="c1",
            candidate_patch_or_output="fake",
            selected_candidate_hash="sha256:c1",
        )
        assert r.patch_applied is False


class TestH89HarnessOutput:
    def test_h8_9_first_solve_harness_candidate_is_isolated(self):
        r = run_first_solve_harness(
            task_id="t1",
            problem_statement="x",
            evidence_refs=("e1",),
            candidate_id="c1",
            candidate_patch_or_output="fake",
            selected_candidate_hash="sha256:c1",
        )
        assert r.candidate_output_isolated is True

    def test_h8_9_first_solve_harness_verifier_not_run_initially(self):
        r = run_first_solve_harness(
            task_id="t1",
            problem_statement="x",
            evidence_refs=("e1",),
            candidate_id="c1",
            candidate_patch_or_output="fake",
            selected_candidate_hash="sha256:c1",
        )
        assert r.verifier_result == "not_run"

    def test_h8_9_first_solve_harness_public_claim_fails_closed(self):
        r = run_first_solve_harness(
            task_id="t1",
            problem_statement="x",
            evidence_refs=("e1",),
            candidate_id="c1",
            candidate_patch_or_output="fake",
            selected_candidate_hash="sha256:c1",
        )
        assert r.public_claim_allowed is False

    def test_h8_9_first_solve_harness_production_ready_false(self):
        r = run_first_solve_harness(
            task_id="t1",
            problem_statement="x",
            evidence_refs=("e1",),
            candidate_id="c1",
            candidate_patch_or_output="fake",
            selected_candidate_hash="sha256:c1",
        )
        assert r.production_ready is False

    def test_h8_9_first_solve_harness_does_not_mark_task_solved(self):
        r = run_first_solve_harness(
            task_id="t1",
            problem_statement="x",
            evidence_refs=("e1",),
            candidate_id="c1",
            candidate_patch_or_output="fake",
            selected_candidate_hash="sha256:c1",
        )
        assert r.task_solved is False
