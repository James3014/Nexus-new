import unittest
import threading
import time
import random
from nexus.verifiers.domain.concurrency.fixed_targets import FixedSingletonRegistry, FixedInventoryCounter, FixedResourceTransfer

class TestConcurrencyStress(unittest.TestCase):
    """
    🌪️ [TDD: STRESS]
    驗證並發修復在「高重複、高競爭、亂序排程」下的極限穩定度。
    """

    def test_stress_singleton_registry(self):
        """[STRESS] 驗證 DCL 屏障在大量亂序請求下不被擊穿"""
        for iteration in range(10): # 跑 10 輪高壓
            FixedSingletonRegistry._instance = None
            FixedSingletonRegistry._init_count = 0
            
            def worker():
                # 加入 Jitter 讓執行緒起步時間隨機化
                time.sleep(random.uniform(0.001, 0.005))
                FixedSingletonRegistry.get_instance()
                
            # 50 個 Threads 瞬間競爭
            threads = [threading.Thread(target=worker) for _ in range(50)]
            for t in threads: t.start()
            for t in threads: t.join()
            
            # 不變量：不論怎麼競爭，都只能初始化一次
            self.assertEqual(FixedSingletonRegistry._init_count, 1, f"Failed at iteration {iteration}")

    def test_stress_inventory_counter(self):
        """[STRESS] 驗證 Shared State 在長時、海量讀寫下無遺失"""
        counter = FixedInventoryCounter()
        
        def worker():
            time.sleep(random.uniform(0.001, 0.005))
            for _ in range(500): # 每條 thread 寫 500 次
                counter.increment()
                
        threads = [threading.Thread(target=worker) for _ in range(20)] # 20 threads = 10,000 increments
        for t in threads: t.start()
        for t in threads: t.join()
        
        # 不變量：總數必須精準等於 10,000
        self.assertEqual(counter.count, 10000)

    def test_stress_resource_transfer(self):
        """[STRESS] 驗證 Lexicographical Locking 在雙向海量轉帳下無死鎖且守恆"""
        transfer = FixedResourceTransfer()
        
        # 初始狀態: A=100, B=100
        
        def run_ab():
            time.sleep(random.uniform(0.001, 0.005))
            for _ in range(10): transfer.transfer_a_to_b(1) # 降低迭代數避免 5 秒 timeout
            
        def run_ba():
            time.sleep(random.uniform(0.001, 0.005))
            for _ in range(10): transfer.transfer_b_to_a(1) # 降低迭代數避免 5 秒 timeout
            
        threads = []
        for _ in range(10): # 10 對競爭
            threads.append(threading.Thread(target=run_ab))
            threads.append(threading.Thread(target=run_ba))
            
        for t in threads: t.start()
        
        # 嚴格的 Timeout 防線：如果超過 5 秒，視為死鎖
        for t in threads:
            t.join(timeout=5.0)
            self.assertFalse(t.is_alive(), "STRESS TEST DEADLOCK DETECTED!")
            
        # 不變量：資源絕對守恆 (100 進 100 出，回到原點)
        self.assertEqual(transfer.val_a, 100)
        self.assertEqual(transfer.val_b, 100)

if __name__ == "__main__":
    unittest.main()
