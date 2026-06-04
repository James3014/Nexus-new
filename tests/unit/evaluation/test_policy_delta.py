import unittest
from nexus.retry_policy.policy import RetryPolicy
from nexus.feedback.contracts import FailurePattern

class TestPolicyDelta(unittest.TestCase):
    """
    🧪 Task T2: Policy Delta Testing (v26.9)
    職責: 確保策略微調具備「精準度」，不發生廣泛副作用。
    """
    def test_selection_confidence_tuning(self):
        """驗證：針對 low_confidence 的特定策略不影響常規重採樣"""
        # 情境 A: 常規缺失 Import -> 應觸發 RESAMPLE
        p_import = [FailurePattern("IMPORT_ERROR", "x", 0.8)]
        res_a = RetryPolicy.decide(p_import, 3)
        self.assertEqual(res_a.action, "RESAMPLE")

        # 情境 B: 定向攻堅 - 低信心 (模擬新策略)
        # 此處為 TDD 預留位：未來微調 RetryPolicy 後，此測試應通過
        p_low_conf = [FailurePattern("SELECTION_LOW_CONFIDENCE", "x", 0.7)]
        # 目前 RetryPolicy 尚未定義此 Pattern，應回傳 ABSTAIN
        res_b = RetryPolicy.decide(p_low_conf, 3)
        self.assertEqual(res_b.action, "ABSTAIN")

if __name__ == "__main__":
    unittest.main()
