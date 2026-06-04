import threading
from typing import Callable, TypeVar

T = TypeVar('T')

def execute_with_double_checked_lock(lock: threading.Lock, check: Callable[[], bool], action: Callable[[], T]) -> T | None:
    if check():
        with lock:
            if check():
                return action()
    return None
