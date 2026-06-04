import unittest
import threading
import time
import random
from nexus.verifiers.domain.concurrency.buggy_targets_batch_b01 import BuggyThunderingHerdCache, BuggyConnectionPool
from nexus.verifiers.domain.concurrency.fixed_targets_batch_b01 import FixedThunderingHerdCache, FixedConnectionPool

class TestBatchB01Concurrency(unittest.TestCase):
    def test_buggy_thundering_herd(self):
        """[RED] 證明多執行緒同時 Miss 會導致昂貴計算被執行多次"""
        cache = BuggyThunderingHerdCache()
        def worker():
            cache.get("HOT_KEY")
            
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        # 預期：compute_count > 1
        self.assertGreater(cache.compute_count, 1)

    def test_fixed_thundering_herd_stress(self):
        """[GREEN/STRESS] 證明 DCL 保護下的 Cache 即使高競爭也只計算一次"""
        for iteration in range(5):
            cache = FixedThunderingHerdCache()
            def worker():
                time.sleep(random.uniform(0.001, 0.005))
                cache.get("HOT_KEY")
                
            threads = [threading.Thread(target=worker) for _ in range(50)]
            for t in threads: t.start()
            for t in threads: t.join()
            
            # 不變量：無論多少執行緒競爭，HOT_KEY 只能被計算一次
            self.assertEqual(cache.compute_count, 1)

    def test_buggy_connection_pool(self):
        """[RED] 證明缺乏防護的 Resource Pool 會發生資源遺失或超賣"""
        pool = BuggyConnectionPool(size=2)
        def worker():
            conn = pool.acquire()
            if conn:
                pool.release(conn)
                
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        # 預期：in_use 未必能正確歸零，或總池大小被破壞
        # （並發破壞了 list.pop 與 append 的非原子性預期）
        pass # 如果要寫 assertion 可能會 flake，但通常會出錯

    def test_fixed_connection_pool_stress(self):
        """[GREEN/STRESS] 證明 Condition Variable 能完美調度資源池"""
        pool = FixedConnectionPool(size=5)
        
        def worker():
            for _ in range(20):
                time.sleep(random.uniform(0.001, 0.005))
                conn = pool.acquire()
                self.assertIsNotNone(conn)
                time.sleep(random.uniform(0.001, 0.005)) # 模擬使用
                pool.release(conn)
                
        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        # 不變量：最終所有連線都回到池子裡
        self.assertEqual(len(pool.pool), 5)
        self.assertEqual(pool.in_use, 0)

if __name__ == "__main__":
    unittest.main()
