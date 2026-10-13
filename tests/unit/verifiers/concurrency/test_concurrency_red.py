import unittest
import threading
import time
from nexus.verifiers.domain.concurrency.buggy_targets import SingletonRegistry, InventoryCounter, ResourceTransfer

class TestConcurrencyTargetsRed(unittest.TestCase):
    """
    🔴 [TDD: RED]
    驗證這些 Concurrency Targets 確實會發生 Race Condition 與 Deadlock。
    """

    def setUp(self):
        SingletonRegistry._instance = None
        SingletonRegistry._init_count = 0

    def test_target1_singleton_race_happens(self):
        """[Barrier Race Test] 證明沒有 barrier 時，singleton 會被重複初始化"""
        def worker():
            SingletonRegistry.get_instance()
            
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        # 預期：因為 Race Condition，init_count 會大於 1
        self.assertGreater(SingletonRegistry._init_count, 1)

    def test_target2_counter_race_happens(self):
        """[Shared State] 證明沒有 lock 時，加法操作會掉數字"""
        counter = InventoryCounter()
        def worker():
            for _ in range(100):
                counter.increment()
                
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        # 預期：總數少於 1000
        self.assertLess(counter.count, 1000)

    def test_target3_deadlock_happens(self):
        """[Lock Order] 證明 AB/BA 鎖順序會導致 Deadlock"""
        transfer = ResourceTransfer()
        
        # 用一個 daemon thread 來監控是否卡死
        deadlock_detected = False
        
        def run_ab(): transfer.transfer_a_to_b(10)
        def run_ba(): transfer.transfer_b_to_a(10)
        
        t1 = threading.Thread(target=run_ab)
        t2 = threading.Thread(target=run_ba)
        
        t1.start()
        t2.start()
        
        # 只等 0.1 秒，如果還沒結束就是 deadlock 了
        t1.join(timeout=0.1)
        t2.join(timeout=0.1)
        
        if t1.is_alive() and t2.is_alive():
            deadlock_detected = True
            
        self.assertTrue(deadlock_detected)

if __name__ == "__main__":
    unittest.main()
