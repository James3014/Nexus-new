import threading
import time
from typing import Dict
from nexus.verifiers.domain.common_core.state_guards import execute_with_double_checked_lock

class FixedThunderingHerdCache:
    """使用 DCL 解決 Thundering Herd"""
    def __init__(self):
        self._cache = {}
        self.compute_count = 0
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_key_lock(self, key: str):
        if key not in self._locks:
            with self._global_lock:
                if key not in self._locks:
                    self._locks[key] = threading.Lock()
        return self._locks[key]

    def get(self, key: str):
        if key not in self._cache:
            key_lock = self._get_key_lock(key)
            def check(): return key not in self._cache
            def compute():
                time.sleep(0.01)
                self._cache[key] = f"DATA_FOR_{key}"
                self.compute_count += 1
                return self._cache[key]
            
            res = execute_with_double_checked_lock(key_lock, check, compute)
            if res is not None:
                return res
        return self._cache[key]

class FixedConnectionPool:
    """使用 Condition Variable 解決資源池爭用"""
    def __init__(self, size=5):
        self.pool = [f"conn_{i}" for i in range(size)]
        self.in_use = 0
        self._cond = threading.Condition()

    def acquire(self):
        with self._cond:
            while len(self.pool) == 0:
                self._cond.wait() # 等待釋放
            time.sleep(0.001)
            conn = self.pool.pop()
            self.in_use += 1
            return conn

    def release(self, conn):
        with self._cond:
            time.sleep(0.001)
            self.pool.append(conn)
            self.in_use -= 1
            self._cond.notify() # 喚醒等待的執行緒
