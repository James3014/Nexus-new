import pytest
import scripts.benchmarks.free_threading_ref_race as f
import threading
import time

def test_free_threading_weakref_race():
    # 測試 concurrency weakref-access 生存期競態
    for _ in range(50):
        obj = f.HardenedAtomicObject("Target")
        failure_flag = []
        
        def thread_a():
            obj.dec_ref()
            
        def thread_b():
            if obj.get_weak_ref():
                if not obj._is_alive:
                    failure_flag.append(True)
                    
        t2 = threading.Thread(target=thread_b)
        t1 = threading.Thread(target=thread_a)
        t2.start()
        await_sleep = 0.002 # 確保 thread_b 先跑起來並進入 sleep 區間
        time.sleep(await_sleep)
        t1.start()
        t1.join()
        t2.join()
        
        if failure_flag:
            pytest.fail("Soundness Hole detected! Weakref active for Dead Object!")
