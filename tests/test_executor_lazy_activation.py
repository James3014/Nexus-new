import unittest
from scripts.ops.lazy_executor_demo import LazyExecutor

class TestLazyActivation(unittest.TestCase):
    """
    [NEXUS v2.5] TDD Task 5: Lazy Activation
    驗證執行器是否能正確延後重成本能力的啟用。
    """
    def test_lazy_skip_success(self):
        # 模擬證據充足場景
        executor = LazyExecutor(flow="hyper_sprint", risk_score=55)
        executor.run_core_chain()
        triggered = executor.run_optional_if_needed({"evidence_density": 0.8})
        
        self.assertFalse(triggered)
        self.assertEqual(executor.wall_time_saved, 4.3) # 4.0 + 0.3
        self.assertNotIn("codeintel", executor.executed)

    def test_lazy_trigger_on_low_density(self):
        # 模擬證據不足場景
        executor = LazyExecutor(flow="hyper_sprint", risk_score=55)
        executor.run_core_chain()
        triggered = executor.run_optional_if_needed({"evidence_density": 0.2})
        
        self.assertTrue(triggered)
        self.assertIn("codeintel", executor.executed)

if __name__ == "__main__":
    unittest.main()
