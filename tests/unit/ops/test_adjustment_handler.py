import unittest
from nexus.ops.adjustment_handler import AdjustmentHandler

class TestAdjustmentHandlerDeterministic(unittest.TestCase):
    """
    ⚖️ Task 1.3: AdjustmentHandler Deterministic Tests
    驗證自動調節的確定性與冷卻行為，透過注入 clock/uuid 消除環境依賴。
    """

    def setUp(self):
        # 物理重設靜態變數，避免 Test Pollution
        AdjustmentHandler._last_adjustment_time = 0

    def test_adjustment_emits_replayable_fields(self):
        # 注入固定的 ID 與 時間
        fixed_id = "test-id-123"
        fixed_time = 1717430400.0 # 2024-06-04 00:00:00
        
        # 確保 last_time 為 0 以讓第一次執行成功
        AdjustmentHandler._last_adjustment_time = 0
        
        res = AdjustmentHandler.request_adjustment(
            0.4, "SCALE_DOWN", "Low health score",
            clock=lambda: fixed_time,
            id_gen=lambda: fixed_id
        )
        self.assertEqual(res["status"], "EXECUTED")
        self.assertEqual(res["adjustment_id"], fixed_id)
        self.assertEqual(res["timestamp"], fixed_time)

    def test_cooldown_blocks_second_adjustment(self):
        """驗證冷卻時間是否生效 (使用注入時間)"""
        AdjustmentHandler._last_adjustment_time = 0
        t = 10000.0 # 使用較大的時間起始值
        
        res1 = AdjustmentHandler.request_adjustment(0.4, "SCALE_DOWN", "First", clock=lambda: t)
        self.assertEqual(res1["status"], "EXECUTED")
        
        # 10 秒後再次嘗試，應被 COOLDOWN_BLOCKED
        res2 = AdjustmentHandler.request_adjustment(0.5, "SCALE_DOWN", "Second", clock=lambda: t + 10.0)
        self.assertEqual(res2["status"], "COOLDOWN_BLOCKED")

if __name__ == "__main__":
    unittest.main()
