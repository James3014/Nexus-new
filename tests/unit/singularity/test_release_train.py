import unittest
from scripts.governance.release_train import ReleaseTrain

class TestReleaseTrainOrchestration(unittest.TestCase):
    """
    🚂 Task 2.1: ReleaseTrain Orchestration Test
    驗證編排器的閘門阻斷行為，確保非形式化串接。
    """

    def test_ci_gate_fail_terminates_train(self):
        # 模擬 CI Gate 失敗
        train = ReleaseTrain(fitness_gate=lambda: False)
        self.assertFalse(train.execute())

    def test_loop_safety_halt_terminates_train(self):
        # 模擬健康分劇烈抖動
        def oscillating_health():
            return {"ppr": 0.1, "slo": 0.1, "fitness": True, "chaos": False, "history": [1.0, 0.9, 0.1]}
        
        train = ReleaseTrain(health_provider=oscillating_health)
        # 預期會因為 LoopMonitor 偵測到 OSCILLATING 而 Halt
        self.assertFalse(train.execute())

    def test_all_gates_pass_seals_train(self):
        # 模擬全通
        train = ReleaseTrain(fitness_gate=lambda: True, chaos_drill=lambda: "OK")
        self.assertTrue(train.execute())

if __name__ == "__main__":
    unittest.main()
