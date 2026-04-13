import threading
import time
import random


class HardenedAtomicObject:
    def __init__(self, name):
        self.name = name
        self.ref_count = 1
        self._is_alive = True
        self._lock = threading.Lock() # 模擬原子 CAS 指令

    def dec_ref(self):
        with self._lock:
            self.ref_count -= 1
            if self.ref_count == 0:
                # 原子性地標記死亡
                self._is_alive = False

    def get_weak_ref(self):
        # 🛡️ v23 Formal Fix: 在同一個原子視窗中執行 Liveness 檢查
        with self._lock:
            if self._is_alive:
                return True
            return False


def run_once():
    obj = HardenedAtomicObject("Target")
    
    def thread_a():
        obj.dec_ref()

    def thread_b():
        if obj.get_weak_ref():
            if not obj._is_alive:
                print("🚨 [CRITICAL] Soundness Hole: Weakref active for Dead Object!")
                return True
        return False

    t1 = threading.Thread(target=thread_a)
    t2 = threading.Thread(target=thread_b)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

if __name__ == "__main__":
    print("🚀 [Memory Challenge] Running 2000 iterations...")
    for i in range(2000):
        run_once()
