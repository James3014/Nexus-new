import unittest
import threading
import time
import random
from nexus.verifiers.domain.concurrency.buggy_targets_batch_b02 import (
    BuggyIdempotentExecutor, BuggyTokenBucket, BuggyReadWriteRegistry, BuggyProducerConsumer, BuggyAsyncBarrier
)
from nexus.verifiers.domain.concurrency.fixed_targets_batch_b02 import (
    FixedIdempotentExecutor, FixedTokenBucket, FixedReadWriteRegistry, FixedProducerConsumer, FixedAsyncBarrier
)

class TestBatchB02Concurrency(unittest.TestCase):

    def test_idempotent_executor_red(self):
        executor = BuggyIdempotentExecutor()
        def worker(): executor.execute()
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertGreater(executor.call_count, 1)

    def test_idempotent_executor_green_stress(self):
        for _ in range(5):
            executor = FixedIdempotentExecutor()
            def worker(): 
                time.sleep(random.uniform(0.001, 0.005))
                executor.execute()
            threads = [threading.Thread(target=worker) for _ in range(20)]
            for t in threads: t.start()
            for t in threads: t.join()
            self.assertEqual(executor.call_count, 1)

    def test_token_bucket_green_stress(self):
        bucket = FixedTokenBucket(capacity=10)
        success_count = [0]
        lock = threading.Lock()
        def worker():
            time.sleep(random.uniform(0.001, 0.005))
            if bucket.consume():
                with lock: success_count[0] += 1
                
        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(success_count[0], 10)

    def test_read_write_registry_green_stress(self):
        reg = FixedReadWriteRegistry()
        failed = [False]
        def writer():
            for i in range(20):
                time.sleep(random.uniform(0.001, 0.005))
                reg.write(i)
        def reader():
            for _ in range(20):
                time.sleep(random.uniform(0.001, 0.005))
                if not reg.read():
                    failed[0] = True
        threads = [threading.Thread(target=writer) for _ in range(5)] + \
                  [threading.Thread(target=reader) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertFalse(failed[0])

    def test_producer_consumer_green_stress(self):
        pc = FixedProducerConsumer()
        consumed = []
        def producer():
            for i in range(10): pc.produce(i)
        def consumer():
            for _ in range(10): consumed.append(pc.consume())
        t1 = threading.Thread(target=producer)
        t2 = threading.Thread(target=consumer)
        t1.start(); t2.start()
        t1.join(); t2.join()
        self.assertEqual(len(consumed), 10)

    def test_async_barrier_green_stress(self):
        barrier = FixedAsyncBarrier(10)
        completed = [0]
        lock = threading.Lock()
        
        def worker():
            time.sleep(random.uniform(0.001, 0.005))
            with lock: completed[0] += 1
            barrier.done()
            
        def waiter():
            barrier.wait()
            self.assertEqual(completed[0], 10)

        t_wait = threading.Thread(target=waiter)
        t_wait.start()
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        t_wait.join()

if __name__ == "__main__":
    unittest.main()
