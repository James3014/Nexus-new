import threading
import time

class Cache:
    def __init__(self):
        self._store = {}
        self._hits = 0
        self._corruptions = 0
        self._lock = threading.Lock()

    def get_or_compute(self, key, compute_fn):
        with self._lock:
            if key not in self._store:
                time.sleep(0.001)  # Simulate compute time, race window
                self._store[key] = compute_fn()
        return self._store[key]

def test_challenge():
    cache = Cache()
    results = []
    call_count = []

    def worker(worker_id):
        def compute():
            call_count.append(worker_id)
            return f"result_{worker_id}"
        val = cache.get_or_compute("shared_key", compute)
        results.append(val)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All threads should get the SAME value (first computed)
    unique_results = set(results)
    assert len(unique_results) == 1, f"Cache race detected! Multiple values computed: {unique_results}"
    assert len(call_count) == 1, f"Cache computed {len(call_count)} times instead of 1! Race condition!"

if __name__ == "__main__":
    print("🚀 Stress Testing...")
    for _ in range(2000): test_challenge()
