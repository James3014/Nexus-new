import threading
import time
import sys

_instance = None
_lock = threading.Lock()

def get_singleton():
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                time.sleep(0.001)
                _instance = {"id": threading.get_ident()}
    return _instance

def test_challenge():
    results = []
    def worker():
        results.append(id(get_singleton()))

    threads = []
    for i in range(100):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()
    
    unique_instances = set(results)
    if len(unique_instances) > 1:
        print(f"FAILED: Found {len(unique_instances)} unique instances!")
        return False
    return True

if __name__ == "__main__":
    _instance = None
    if not test_challenge():
        sys.exit(1)
    else:
        print("SUCCESS")
        sys.exit(0)
