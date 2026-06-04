import threading
from typing import List

def acquire_locks_lexicographically(locks: List[threading.Lock]) -> List[threading.Lock]:
    sorted_locks = sorted(locks, key=id)
    for lock in sorted_locks:
        lock.acquire()
    return sorted_locks

def release_locks(locks: List[threading.Lock]):
    for lock in reversed(locks):
        lock.release()
