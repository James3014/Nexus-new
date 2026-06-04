import threading
from typing import Any, Callable, TypeVar, Generic

T = TypeVar('T')

class ConcurrencyCore:
    """
    🛠️ Task: Concurrency Common Core (Domain/Infrastructure)
    職責: 將修復 Race Condition 與 Deadlock 的共用模式抽象化。
    此底座將作為後續所有 Concurrency 題型的基礎。
    """
    
    @staticmethod
    def execute_with_double_checked_lock(lock: threading.Lock, 
                                        check_condition: Callable[[], bool], 
                                        action: Callable[[], T]) -> T | None:
        """
        抽象化 Double-Checked Locking (DCL) 模式。
        用來解決 Lazy Initialization 時的 Barrier Race。
        """
        if check_condition():
            with lock:
                if check_condition():
                    return action()
        return None

    @staticmethod
    def acquire_locks_lexicographically(locks: List[threading.Lock]) -> List[threading.Lock]:
        """
        抽象化 Lexicographical Locking 模式。
        依據鎖的記憶體位置 (id) 進行排序，強制全局一致的獲取順序，以避免 AB/BA Deadlock。
        """
        # 注意: 這裡使用 id(lock) 作為排序依據，確保順序絕對一致
        sorted_locks = sorted(locks, key=id)
        for lock in sorted_locks:
            lock.acquire()
        return sorted_locks

    @staticmethod
    def release_locks(locks: List[threading.Lock]):
        """
        釋放鎖 (依賴反向釋放原則)
        """
        for lock in reversed(locks):
            lock.release()
