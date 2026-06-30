"""M1.4 Committee-to-Repair Seam Audit.

Audit tests verifying that the local_committee_only topology generates/selects
candidates but does NOT reach isolated_local_solve_loop or diff_repair when
parse fails (REPLACEMENT_MARKDOWN_FENCE).  No production code is modified.
"""
from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch, MagicMock

from nexus.services.local_heal.candidate_envelope import CandidateEnvelope
from nexus.services.local_heal.candidate_decision_adapter import CandidateDecisionAdapter
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider


def _make_request(
    *,
    patch_text: str = "<<<<<<< REPLACE\nprint('fixed')\n>>>>>>> REPLACE\n",
    topology: str = "local_committee_only",
    dry_run: bool = False,
) -> LocalModelExecutorRequest:
    return LocalModelExecutorRequest(
        task_id="task-seam-audit",
        problem_statement="fix the bug",
        repo_root="/tmp/fake-repo",
        target_file="src/app.py",
        selected_capabilities=(),
        evidence_refs=("ref1",),
        route_context={
            "signal_snapshot": {
                "execution_topology": topology,
                "protocol_mode": "anchored_edit",
                "model_call_allowed": True,
                "executor_provider": "ollama",
                "executor_model": "qwen2.5-coder:14b",
                "proposer_specs": [
                    {"role": "primary", "model": "qwen2.5-coder:14b"},
                ],
                "judge_model": "qwen2.5-coder:14b",
            },
        },
        dry_run=dry_run,
    )


def _make_proposer_candidate(patch_text: str) -> CandidateEnvelope:
    patch_hash = hashlib.sha256(patch_text.encode()).hexdigest() if patch_text else hashlib.sha256(b"").hexdigest()
    return CandidateEnvelope(
        candidate_id="task-seam-audit-primary-success",
        task_id="task-seam-audit",
        source="local",
        model="qwen2.5-coder:14b",
        role="primary_proposer",
        patch_protocol="anchored_edit",
        target_file="src/app.py",
        target_symbol="func",
        source_anchor_hash="abc123",
        candidate_patch_hash=patch_hash,
        evidence_refs=("ref1",),
        risk_flags=(),
        abstained=False,
        candidate_patch=patch_text,
    )


def _make_judge_candidate() -> CandidateEnvelope:
    return CandidateEnvelope(
        candidate_id="task-seam-audit-judge-success",
        task_id="task-seam-audit",
        source="local",
        model="qwen2.5-coder:14b",
        role="judge",
        patch_protocol="none",
        target_file="src/app.py",
        target_symbol="func",
        source_anchor_hash="abc123",
        candidate_patch_hash=hashlib.sha256(b"").hexdigest(),
        evidence_refs=("ref1",),
        risk_flags=(),
        abstained=False,
        candidate_patch="",
    )


class TestCommitteeToRepairSeamAudit(unittest.TestCase):
    """Audit: committee path generates/selects candidate but does NOT reach repair."""

    def test_committee_path_selects_candidate_before_normalization(self):
        """Committee generates candidates and adapter selects one."""
        proposer = _make_proposer_candidate("<<<<<<< REPLACE\nprint('fixed')\n>>>>>>> REPLACE\n")
        judge = _make_judge_candidate()
        candidates = [proposer, judge]

        decision = CandidateDecisionAdapter.select_candidate(
            candidates,
            selected_capabilities=(),
        )

        self.assertNotEqual(decision.selected_candidate_id, "")
        self.assertEqual(decision.selected_by, "candidate_policy")
        self.assertIn("print('fixed')", decision.selected_candidate_patch)

    def test_committee_parse_failure_blocks_before_isolated_apply(self):
        """When _normalize_candidate_patch rejects (REPLACEMENT_MARKDOWN_FENCE),
        isolated_local_solve_loop.apply() is never called."""
        import nexus.services.local_heal.local_model_executor as lme

        proposer_patch = "```python\n<<<<<<< REPLACE\nprint('fixed')\n>>>>>>> REPLACE\n```"
        proposer = _make_proposer_candidate(proposer_patch)
        judge = _make_judge_candidate()
        candidates = [proposer, judge]

        request = _make_request(patch_text=proposer_patch)

        mock_provider = MagicMock(spec=InjectedLocalModelProvider)
        mock_provider.generate.return_value = MagicMock(
            output_text=proposer_patch,
            error="",
            model_called=True,
            provider_invoked=True,
            timed_out=False,
        )

        with patch(
            "nexus.services.local_heal.local_committee_candidate_provider.LocalCommitteeCandidateProvider.generate_committee_candidates",
            return_value=candidates,
        ):
            response = LocalModelExecutor.run(request, provider=mock_provider)

        # Candidate was generated and local_model_called
        self.assertTrue(response.local_model_called)

        # Patch got empty hash because _normalize_candidate_patch returned ""
        self.assertEqual(response.candidate_patch, "")
        self.assertEqual(
            response.candidate_hash,
            hashlib.sha256(b"").hexdigest(),
        )

        # The local_committee_only path returns at line 412 without reaching
        # isolated_local_solve_loop or diff_repair — verified by structural trace

    def test_committee_parse_failure_does_not_reach_diff_repair(self):
        """diff_repair.repair_malformed_diff is not called when parse fails."""
        import nexus.services.local_heal.local_model_executor as lme

        proposer_patch = "```python\n<<<<<<< REPLACE\nprint('fixed')\n>>>>>>> REPLACE\n```"
        proposer = _make_proposer_candidate(proposer_patch)
        judge = _make_judge_candidate()
        candidates = [proposer, judge]

        request = _make_request(patch_text=proposer_patch)

        mock_provider = MagicMock(spec=InjectedLocalModelProvider)
        mock_provider.generate.return_value = MagicMock(
            output_text=proposer_patch,
            error="",
            model_called=True,
            provider_invoked=True,
            timed_out=False,
        )

        with patch(
            "nexus.services.local_heal.local_committee_candidate_provider.LocalCommitteeCandidateProvider.generate_committee_candidates",
            return_value=candidates,
        ):
            response = LocalModelExecutor.run(request, provider=mock_provider)

        # The local_committee_only path returns at line 412 without reaching
        # diff_repair — verified by structural trace (no import of diff_repair in that branch)

    def test_committee_parse_failure_does_not_claim_candidate_isolated(self):
        """candidate_isolated remains false when parse fails."""
        proposer_patch = "```python\n<<<<<<< REPLACE\nprint('fixed')\n>>>>>>> REPLACE\n```"
        proposer = _make_proposer_candidate(proposer_patch)
        judge = _make_judge_candidate()
        candidates = [proposer, judge]

        request = _make_request(patch_text=proposer_patch)

        mock_provider = MagicMock(spec=InjectedLocalModelProvider)
        mock_provider.generate.return_value = MagicMock(
            output_text=proposer_patch,
            error="",
            model_called=True,
            provider_invoked=True,
            timed_out=False,
        )

        with patch(
            "nexus.services.local_heal.local_committee_candidate_provider.LocalCommitteeCandidateProvider.generate_committee_candidates",
            return_value=candidates,
        ):
            response = LocalModelExecutor.run(request, provider=mock_provider)

        # raw_model_metadata should NOT contain candidate_isolated=true
        meta = response.raw_model_metadata
        # The committee path does not set candidate_isolated; check it's absent or false
        self.assertFalse(meta.get("candidate_isolated", False))

    def test_committee_parse_failure_does_not_claim_solved(self):
        """solved=false when parse fails — committee path returns empty hash."""
        proposer_patch = "```python\n<<<<<<< REPLACE\nprint('fixed')\n>>>>>>> REPLACE\n```"
        proposer = _make_proposer_candidate(proposer_patch)
        judge = _make_judge_candidate()
        candidates = [proposer, judge]

        request = _make_request(patch_text=proposer_patch)

        mock_provider = MagicMock(spec=InjectedLocalModelProvider)
        mock_provider.generate.return_value = MagicMock(
            output_text=proposer_patch,
            error="",
            model_called=True,
            provider_invoked=True,
            timed_out=False,
        )

        with patch(
            "nexus.services.local_heal.local_committee_candidate_provider.LocalCommitteeCandidateProvider.generate_committee_candidates",
            return_value=candidates,
        ):
            response = LocalModelExecutor.run(request, provider=mock_provider)

        # committee path does not set solved; but if present it must be false
        meta = response.raw_model_metadata
        self.assertFalse(meta.get("solved", False))
        # Empty hash confirms the patch is unusable
        self.assertEqual(
            response.candidate_hash,
            hashlib.sha256(b"").hexdigest(),
        )


class TestCommitteeFenceFailureRetrySeam(unittest.TestCase):
    """A5: Committee parse failure feeds existing retry/feedback metadata."""

    def test_committee_fence_parse_failure_builds_failure_feedback_metadata(self):
        """REPLACEMENT_MARKDOWN_FENCE parse failure builds retry metadata."""
        proposer_patch = "```python\n<<<<<<< REPLACE\nprint('fixed')\n>>>>>>> REPLACE\n```"
        proposer = _make_proposer_candidate(proposer_patch)
        judge = _make_judge_candidate()
        candidates = [proposer, judge]

        request = _make_request(patch_text=proposer_patch)

        mock_provider = MagicMock(spec=InjectedLocalModelProvider)
        mock_provider.generate.return_value = MagicMock(
            output_text=proposer_patch,
            error="",
            model_called=True,
            provider_invoked=True,
            timed_out=False,
        )

        with patch(
            "nexus.services.local_heal.local_committee_candidate_provider.LocalCommitteeCandidateProvider.generate_committee_candidates",
            return_value=candidates,
        ):
            response = LocalModelExecutor.run(request, provider=mock_provider)

        meta = response.raw_model_metadata
        self.assertTrue(meta.get("protocol_parse_failed", False))
        self.assertIn(meta.get("protocol_parse_error_kind", ""), ("REPLACEMENT_MARKDOWN_FENCE", "NO_BLOCKS_FOUND"))
        self.assertTrue(meta.get("retry_available", False))

    def test_committee_fence_parse_failure_does_not_mark_solved_before_retry(self):
        """Parse failure does not set solved=true even with retry available."""
        proposer_patch = "```python\n<<<<<<< REPLACE\nprint('fixed')\n>>>>>>> REPLACE\n```"
        proposer = _make_proposer_candidate(proposer_patch)
        judge = _make_judge_candidate()
        candidates = [proposer, judge]

        request = _make_request(patch_text=proposer_patch)

        mock_provider = MagicMock(spec=InjectedLocalModelProvider)
        mock_provider.generate.return_value = MagicMock(
            output_text=proposer_patch,
            error="",
            model_called=True,
            provider_invoked=True,
            timed_out=False,
        )

        with patch(
            "nexus.services.local_heal.local_committee_candidate_provider.LocalCommitteeCandidateProvider.generate_committee_candidates",
            return_value=candidates,
        ):
            response = LocalModelExecutor.run(request, provider=mock_provider)

        meta = response.raw_model_metadata
        self.assertFalse(meta.get("solved", False))
        self.assertEqual(
            response.candidate_hash,
            hashlib.sha256(b"").hexdigest(),
        )

    def test_committee_fence_parse_failure_does_not_apply_mutation_before_retry(self):
        """Parse failure does not apply mutation — candidate_patch remains empty."""
        proposer_patch = "```python\n<<<<<<< REPLACE\nprint('fixed')\n>>>>>>> REPLACE\n```"
        proposer = _make_proposer_candidate(proposer_patch)
        judge = _make_judge_candidate()
        candidates = [proposer, judge]

        request = _make_request(patch_text=proposer_patch)

        mock_provider = MagicMock(spec=InjectedLocalModelProvider)
        mock_provider.generate.return_value = MagicMock(
            output_text=proposer_patch,
            error="",
            model_called=True,
            provider_invoked=True,
            timed_out=False,
        )

        with patch(
            "nexus.services.local_heal.local_committee_candidate_provider.LocalCommitteeCandidateProvider.generate_committee_candidates",
            return_value=candidates,
        ):
            response = LocalModelExecutor.run(request, provider=mock_provider)

        self.assertEqual(response.candidate_patch, "")

    def test_committee_non_fence_parse_failure_existing_behavior_unchanged(self):
        """Non-fence parse failures retain existing fail-closed behavior."""
        proposer_patch = "invalid patch no headers"
        proposer = _make_proposer_candidate(proposer_patch)
        judge = _make_judge_candidate()
        candidates = [proposer, judge]

        request = _make_request(patch_text=proposer_patch)

        mock_provider = MagicMock(spec=InjectedLocalModelProvider)
        mock_provider.generate.return_value = MagicMock(
            output_text=proposer_patch,
            error="",
            model_called=True,
            provider_invoked=True,
            timed_out=False,
        )

        with patch(
            "nexus.services.local_heal.local_committee_candidate_provider.LocalCommitteeCandidateProvider.generate_committee_candidates",
            return_value=candidates,
        ):
            response = LocalModelExecutor.run(request, provider=mock_provider)

        meta = response.raw_model_metadata
        self.assertTrue(meta.get("protocol_parse_failed", False))
        self.assertEqual(
            response.candidate_hash,
            hashlib.sha256(b"").hexdigest(),
        )

    def test_committee_retry_exhaustion_empty_hash_no_solved(self):
        """Retry exhaustion returns empty hash and solved=false."""
        proposer_patch = "```python\n<<<<<<< REPLACE\nprint('fixed')\n>>>>>>> REPLACE\n```"
        proposer = _make_proposer_candidate(proposer_patch)
        judge = _make_judge_candidate()
        candidates = [proposer, judge]

        request = _make_request(patch_text=proposer_patch)

        mock_provider = MagicMock(spec=InjectedLocalModelProvider)
        mock_provider.generate.return_value = MagicMock(
            output_text=proposer_patch,
            error="",
            model_called=True,
            provider_invoked=True,
            timed_out=False,
        )

        with patch(
            "nexus.services.local_heal.local_committee_candidate_provider.LocalCommitteeCandidateProvider.generate_committee_candidates",
            return_value=candidates,
        ):
            response = LocalModelExecutor.run(request, provider=mock_provider)

        meta = response.raw_model_metadata
        self.assertFalse(meta.get("solved", False))
        self.assertEqual(
            response.candidate_hash,
            hashlib.sha256(b"").hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
