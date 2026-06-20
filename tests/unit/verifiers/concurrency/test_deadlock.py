import unittest
import threading
import os
from nexus.verifiers.domain.concurrency.buggy_targets import ResourceTransfer

class TestConcurrencyDeadlock(unittest.TestCase):
    def test_target3_deadlock_fixed(self):
        """[Lock Order] 證明 Lexicographical Locking 成功解除 Deadlock"""
        transfer = ResourceTransfer()
        
        deadlock_detected = False
        
        def run_ab(): transfer.transfer_a_to_b(10)
        def run_ba(): transfer.transfer_b_to_a(10)
        
        t1 = threading.Thread(target=run_ab, daemon=True)
        t2 = threading.Thread(target=run_ba, daemon=True)
        
        t1.start()
        t2.start()
        
        # 等待 1.0 秒，若未 deadlock 應在 0.05 秒內完成
        t1.join(timeout=1.0)
        t2.join(timeout=1.0)
        
        if t1.is_alive() and t2.is_alive():
            deadlock_detected = True
            
        if deadlock_detected:
            print("BUG PRESENT: deadlock detected, exiting cleanly to prevent hang")
            os._exit(1)
            
        self.assertFalse(deadlock_detected)
        self.assertEqual(transfer.val_a, 100)
        self.assertEqual(transfer.val_b, 100)

if __name__ == "__main__":
    unittest.main()
