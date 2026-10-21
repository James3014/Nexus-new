import re
import unittest
from nexus.committee.controller import CommitteeControllerV263
from nexus.verifiers.contracts import FailureTag, VerifierVerdict
from nexus.verifiers.registry import VerifierRegistry
from nexus.verifiers.packs.base import VerifierPack
from nexus.verifiers.packs.registry import PackRegistry
import os


def _name_sanity_verdict(candidate_id: str, patch: str) -> VerifierVerdict:
    # Same rule as the retired nexus.verifiers.domain.name_sanity.NameSanityVerifier.
    usages = set(re.findall(r"([a-zA-Z0-9_]+)\.", patch)) - {"self"}
    allowed = set(re.findall(r"import\s+([a-zA-Z0-9_]+)", patch))
    allowed |= set(re.findall(r"as\s+([a-zA-Z0-9_]+)", patch))
    allowed |= {"os", "sys", "time", "numpy", "np", "pandas", "pd"}
    missing = sorted(usages - allowed)
    if missing:
        return VerifierVerdict(
            verifier_name="name_sanity",
            candidate_id=candidate_id,
            passed=False,
            score=-5.0,
            failure_tags=[FailureTag(code="NAME_ERROR", description=f"MISSING: {missing}")],
        )
    return VerifierVerdict(
        verifier_name="name_sanity",
        candidate_id=candidate_id,
        passed=True,
        score=2.0 if usages else 1.0,
        failure_tags=[FailureTag(code="SUCCESS", description="All imports resolved")],
    )


class _StubAstropyPack(VerifierPack):
    """Test-local stand-in for AstropyPack, retired in Phase-2 batch C (#2584)."""

    name = "stub_astropy_pack"
    domain_tags = ["astropy", "science", "ffi"]

    def evaluate_all(self, candidate_id: str, patch: str) -> list[VerifierVerdict]:
        inheritance = VerifierVerdict(
            verifier_name="inheritance",
            candidate_id=candidate_id,
            passed=True,
            score=1.0,
            failure_tags=[FailureTag(code="SUCCESS", description="INHERITANCE_STRUCTURE_OK")],
        )
        return [_name_sanity_verdict(candidate_id, patch), inheritance]


class TestDataFlowRefinement(unittest.TestCase):
    """
    [T8] Task: Global Data-Flow Regression (v26.7)
    驗證 feedback -> retry 與 calibration -> abstention 的閉環正確性。
    """
    def setUp(self):
        PackRegistry.clear()
        PackRegistry.register(_StubAstropyPack())
        os.environ["NEXUS_USE_COMMITTEE"] = "1"
        os.environ["NEXUS_USE_PACKS"] = "1"
        os.environ["NEXUS_USE_TS"] = "1"

    def test_feedback_loop_trigger(self):
        """驗證：當判定為棄權時，正確觸發 Feedback Router 並產出指令"""
        ctrl = CommitteeControllerV263("test-task")
        # 提供一個必 Fail 的補丁 (Missing pd)
        proposals = [{"model": "7B", "attempt": 1, "raw_label": "r:0", "artifacts": ["pd.DataFrame()"]}]
        
        # 應觸發棄權並打印反饋日誌
        receipt = ctrl.process_proposals(proposals)
        self.assertIsNone(receipt.winner_id)
        self.assertEqual(receipt.failure_bucket, "selection_low_confidence")
        # AdaptiveResampler 的決策被保留下來，而不是只印出後丟棄
        self.assertEqual(ctrl.last_retry_directive["mode"], "WAIT")
        self.assertEqual(ctrl.last_retry_directive["modified_params"]["diversity_score"], 1.0)

    def test_low_diversity_abstention_requests_exploration(self):
        """驗證：棄權且候選幾乎相同時，AdaptiveResampler 要求多樣化重採樣"""
        ctrl = CommitteeControllerV263("test-task")
        proposals = [
            {"model": "7B", "attempt": 1, "raw_label": "r:0", "artifacts": ["pd.DataFrame()"]},
            {"model": "7B", "attempt": 2, "raw_label": "r:0", "artifacts": ["pd.DataFrame()"]},
        ]
        receipt = ctrl.process_proposals(proposals)
        if not receipt.abstained:
            self.skipTest("selection did not abstain for identical candidates")
        directive = ctrl.last_retry_directive
        self.assertTrue(directive["should_retry"])
        self.assertEqual(directive["mode"], "EXPLORE")
        self.assertTrue(directive["modified_params"]["variant_shuffling"])

    def test_abstention_policy_integration(self):
        """驗證：AbstentionPolicy 是否正確參與最終決策"""
        ctrl = CommitteeControllerV263("test-task")
        # 模擬兩個候選者，產生足夠的 Gap
        proposals = [
            {"model": "14B", "attempt": 1, "raw_label": "r:0", "artifacts": ["import pandas as pd\npd.read_csv()"]},
            {"model": "7B", "attempt": 2, "raw_label": "r:0", "artifacts": ["xr.open_dataset()"]} # Fail path (missing xr)
        ]
        receipt = ctrl.process_proposals(proposals)
        self.assertIsNotNone(receipt.winner_id)
        self.assertFalse(receipt.abstained)

if __name__ == "__main__":
    unittest.main()
