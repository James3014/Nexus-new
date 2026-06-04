import unittest
from nexus.governance.loop_monitor import LoopMonitor

class TestLoopMonitorContract(unittest.TestCase):
    """
    👁️ Task 1.2: LoopMonitor Contract Tests
    驗證振盪偵測與安全停機契約，確保不會因歷史不足而誤殺。
    """

    def test_insufficient_history_no_halt(self):
        # 只有 2 筆，低於 3 筆下限
        res = LoopMonitor.evaluate_loop_stability([0.9, 0.1])
        self.assertEqual(res["status"], "INSUFFICIENT_DATA")
        self.assertFalse(res["safety_halt"])

    def test_oscillation_halt(self):
        # 劇烈抖動
        res = LoopMonitor.evaluate_loop_stability([1.0, 0.2, 0.9, 0.1])
        self.assertEqual(res["status"], "OSCILLATING")
        self.assertTrue(res["safety_halt"])

    def test_stable_loop_no_halt(self):
        # 穩定上升或持平
        res = LoopMonitor.evaluate_loop_stability([0.9, 0.92, 0.93])
        self.assertEqual(res["status"], "META_STABLE")
        self.assertFalse(res["safety_halt"])

    def test_compatibility_shim(self):
        """Red: 驗證 detect_oscillation 靜態方法是否保持舊 consumer 兼容"""
        # 目前版本 detect_oscillation 可能回傳 True/False，應與 evaluate_loop_stability 對齊
        # 注意：目前的實作 detect_oscillation 回傳 True 代表偵測到振盪（危險）
        is_unstable = LoopMonitor.detect_oscillation([1.0, 0.2, 0.9, 0.1])
        self.assertTrue(is_unstable)

if __name__ == "__main__":
    unittest.main()
