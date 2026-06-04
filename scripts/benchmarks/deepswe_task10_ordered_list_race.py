import threading
import time
import bisect

class OrderedLog:
    def __init__(self):
        self._entries = []
        self._lock = threading.Lock()

    def insert(self, priority, value):
        with self._lock:
            pos = bisect.bisect_left(self._entries, (priority,))
            self._entries.insert(pos, (priority, value))

    def is_sorted(self):
        return all(self._entries[i][0] <= self._entries[i+1][0]
                   for i in range(len(self._entries)-1))

def test_challenge():
    log = OrderedLog()
    import random
    random.seed(42)
    priorities = [random.randint(1, 100) for _ in range(50)]

    threads = [threading.Thread(target=log.insert, args=(p, f"entry_{p}")) for p in priorities]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(log._entries) == 50, f"Lost entries! Expected 50 but got {len(log._entries)}"
    assert log.is_sorted(), f"Ordering race detected! List is not sorted after concurrent inserts"


if __name__ == "__main__":
    print("🚀 Stress Testing...")
    for _ in range(2000): test_challenge()
