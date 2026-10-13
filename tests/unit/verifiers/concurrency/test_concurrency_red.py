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
        """[Lock Order] 證明 AB/BA 鎖順序會導致 Deadlock

        buggy_targets.ResourceTransfer itself was repaired in place by
        ac87243dc (pinned by test_deadlock.py), so its transfer methods no
        longer invert the lock order. This RED case reproduces the original
        AB/BA inversion on the target's own locks. A barrier makes both
        threads hold their first lock before reaching for the second, and
        the second acquire uses a timeout so no thread is left hung (#1928).
        """
        transfer = ResourceTransfer()
        both_hold_first = threading.Barrier(2)
        blocked = {}

        def run(first, second, name):
            with first:
                both_hold_first.wait(timeout=5)
                got_second = second.acquire(timeout=0.2)
                if got_second:
                    second.release()
                blocked[name] = not got_second
                both_hold_first.wait(timeout=5)

        t1 = threading.Thread(target=run, args=(transfer.lock_a, transfer.lock_b, "ab"), daemon=True)
        t2 = threading.Thread(target=run, args=(transfer.lock_b, transfer.lock_a, "ba"), daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        deadlock_detected = blocked.get("ab") is True and blocked.get("ba") is True
        self.assertTrue(deadlock_detected)


if __name__ == "__main__":
    unittest.main()
