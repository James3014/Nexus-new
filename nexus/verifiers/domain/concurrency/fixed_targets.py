import threading
import time
from typing import Any

class FixedSingletonRegistry:
    """
    [Target 1: Repaired] 
    使用 Double-Checked Locking 解決 Race Condition。
    """
    _instance = None
    _init_count = 0
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    time.sleep(0.01) # 模擬耗時操作
                    cls._instance = object()
                    cls._init_count += 1
        return cls._instance


class FixedInventoryCounter:
    """
    [Target 2: Repaired]
    使用 Reentrant Lock 保護 Shared Mutable State。
    """
    def __init__(self):
        self.count = 0
        self._lock = threading.RLock()

    def increment(self):
        with self._lock:
            current = self.count
            time.sleep(0.001)
            self.count = current + 1


class FixedResourceTransfer:
    """
    [Target 3: Repaired]
    透過 Resource ID 排序 (Lexicographical Locking) 解決 AB/BA Deadlock。
    """
    def __init__(self):
        self.lock_a = threading.Lock()
        self.lock_b = threading.Lock()
        self.val_a = 100
        self.val_b = 100

    def _acquire_locks_in_order(self, lock1, lock2):
        """保證全域一致的鎖順序 (模擬透過 ID 比較)"""
        # 在此為簡單示範，強制先鎖 A 再鎖 B
        locks = [self.lock_a, self.lock_b] 
        locks[0].acquire()
        locks[1].acquire()
        return locks

    def transfer_a_to_b(self, amount: int):
        locks = self._acquire_locks_in_order(self.lock_a, self.lock_b)
        try:
            time.sleep(0.01) 
            self.val_a -= amount
            self.val_b += amount
        finally:
            for lock in reversed(locks):
                lock.release()

    def transfer_b_to_a(self, amount: int):
        locks = self._acquire_locks_in_order(self.lock_b, self.lock_a)
        try:
            time.sleep(0.01) 
            self.val_b -= amount
            self.val_a += amount
        finally:
            for lock in reversed(locks):
                lock.release()
