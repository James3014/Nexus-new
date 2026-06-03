import unittest
from nexus.committee.controller import CommitteeControllerV263
from nexus.verifiers.registry import VerifierRegistry
from nexus.verifiers.packs.registry import PackRegistry
from nexus.verifiers.packs.astropy_pack import AstropyPack
import os

class TestDataFlowRefinement(unittest.TestCase):
    """
    [T8] Task: Global Data-Flow Regression (v26.7)
    驗證 feedback -> retry 與 calibration -> abstention 的閉環正確性。
    """
    def setUp(self):
        PackRegistry.clear()
        PackRegistry.register(AstropyPack())
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
