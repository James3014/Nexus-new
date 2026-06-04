import unittest
from nexus.verifiers.contracts import VerifierVerdict, EvidenceRef, FailureTag

class TestVerifierContracts(unittest.TestCase):
    def test_verdict_schema(self):
        """[T5] 驗證：VerifierVerdict 能正確封裝局部證據與失敗標籤"""
        verdict = VerifierVerdict(
            verifier_name="name_sanity",
            candidate_id="c-001",
            passed=False,
            score=-5.0,
            evidence_refs=[EvidenceRef(source_file="test.py", snippet="np.arange(10)")],
            failure_tags=[FailureTag(code="MISSING_IMPORT", description="np is not defined")],
            confidence=0.9
        )
        self.assertFalse(verdict.passed)
        self.assertEqual(len(verdict.evidence_refs), 1)
        self.assertEqual(verdict.failure_tags[0].code, "MISSING_IMPORT")

if __name__ == "__main__":
    unittest.main()
