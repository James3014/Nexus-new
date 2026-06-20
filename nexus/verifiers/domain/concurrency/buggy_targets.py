import threading
import time

class SingletonRegistry:
    """
    [Target 1: Barrier Race Test]
    模擬問題: 多執行緒同時初始化，導致 Singleton 被建立多次。
    """
    _instance = None
    _init_count = 0

    @classmethod
    def get_instance(cls):
        # 故意放大的 Race Window
        if cls._instance is None:
            time.sleep(0.01) # Force race
            cls._instance = object()
            cls._init_count += 1
        return cls._instance

class InventoryCounter:
    """
    [Target 2: Shared State Atomicity]
    模擬問題: 非原子性的 += 1 導致庫存計算遺失。
    """
    def __init__(self):
        self.count = 0

    def increment(self):
        # 故意拆分讀寫的 Race Window
        current = self.count
        time.sleep(0.001)
        self.count = current + 1

class ResourceTransfer:
    """
    [Target 3: Deadlock / Lock Order]
    模擬問題: AB/BA 鎖順序不一致導致的死鎖風險。
    """
    def __init__(self):
        self.lock_a = threading.Lock()
        self.lock_b = threading.Lock()
        self.val_a = 100
        self.val_b = 100

    def _acquire_locks_in_order(self, lock1, lock2):
        # Force consistent global lock order: lock_a first, then lock_b
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
