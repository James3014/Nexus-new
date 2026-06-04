import unittest
import threading
import time
from nexus.verifiers.domain.concurrency.fixed_targets import FixedSingletonRegistry, FixedInventoryCounter, FixedResourceTransfer

class TestConcurrencyTargetsGreen(unittest.TestCase):
    """
    🟢 [TDD: GREEN]
    驗證修復後的 Targets 已經徹底消除 Race Condition 與 Deadlock。
    """

    def setUp(self):
        FixedSingletonRegistry._instance = None
        FixedSingletonRegistry._init_count = 0

    def test_target1_singleton_race_fixed(self):
        """[Barrier Race Test] 證明 DCL 成功阻斷重複初始化"""
        def worker():
            FixedSingletonRegistry.get_instance()
            
        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        # 預期：即使多執行緒競爭，也只會初始化一次
        self.assertEqual(FixedSingletonRegistry._init_count, 1)

    def test_target2_counter_race_fixed(self):
        """[Shared State] 證明 lock 成功保證原子更新"""
        counter = FixedInventoryCounter()
        def worker():
            for _ in range(100):
                counter.increment()
                
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        # 預期：總數精準為 1000，毫無遺失
        self.assertEqual(counter.count, 1000)

    def test_target3_deadlock_fixed(self):
        """[Lock Order] 證明 Lexicographical Locking 成功解除 Deadlock"""
        transfer = FixedResourceTransfer()
        
        deadlock_detected = False
        
        def run_ab(): transfer.transfer_a_to_b(10)
        def run_ba(): transfer.transfer_b_to_a(10)
        
        t1 = threading.Thread(target=run_ab)
        t2 = threading.Thread(target=run_ba)
        
        t1.start()
        t2.start()
        
        # 等待 1 秒，若未 deadlock 應在 0.05 秒內完成
        t1.join(timeout=1.0)
        t2.join(timeout=1.0)
        
        if t1.is_alive() and t2.is_alive():
            deadlock_detected = True
            
        self.assertFalse(deadlock_detected)
        self.assertEqual(transfer.val_a, 100) # -10 + 10 = 100
        self.assertEqual(transfer.val_b, 100)

if __name__ == "__main__":
    unittest.main()
