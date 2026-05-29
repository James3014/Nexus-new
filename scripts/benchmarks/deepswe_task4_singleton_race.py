import threading

_instance = None
_lock = threading.Lock()

def get_singleton():
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                import time
                time.sleep(0.001)  # Simulate some work
                _instance = {"value": threading.current_thread().ident, "created_by": threading.current_thread().name}
    return _instance

def reset():
    global _instance
    with _lock:
        _instance = None

def test_challenge():
    reset()
    results = []
    errors = []

    def worker():
        obj = get_singleton()
        results.append(id(obj))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    unique_ids = set(results)
    assert len(unique_ids) == 1, f"Singleton race detected! Multiple instances created: {len(unique_ids)} unique objects"

if __name__ == "__main__":
    test_challenge()