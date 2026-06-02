import unittest
import json
from nexus.committee.models import ProposalCandidate, CriticVerdict, CommitteeReceipt

class TestCommitteeModels(unittest.TestCase):
    def test_candidate_serialization(self):
        """驗證提案候選者 Schema 正確性"""
        c = ProposalCandidate(
            candidate_id="c-001",
            source_model="7B",
            attempt_id=1,
            raw_label="r:0,p:1",
            normalized_phase="PLAN",
            artifact_refs=["p-01.json"]
        )
        self.assertEqual(c.candidate_id, "c-001")
        self.assertEqual(len(c.artifact_refs), 1)

    def test_receipt_structure(self):
        """驗證委員會收據結構"""
        r = CommitteeReceipt(
            task_id="task-99",
            k=3,
            candidates=[],
            verdicts=[],
            winner_id=None,
            failure_bucket="coverage_failure"
        )
        self.assertEqual(r.failure_bucket, "coverage_failure")

if __name__ == "__main__":
    unittest.main()
