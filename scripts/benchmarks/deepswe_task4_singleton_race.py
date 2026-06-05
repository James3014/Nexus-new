import threading
import time
import sys

_instance = None

def get_singleton():
    global _instance
    with threading.Lock():
        if _instance is None:
            _instance = {"id": threading.get_ident()}
    return _instance

def test_challenge():
    results = []
    def worker():
        results.append(id(get_singleton()))

    threads = []
    # 🚀 增加並發量到 500
    for i in range(500):
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
    _instance = None # Reset
    if not test_challenge():
        sys.exit(1)
    else:
        print("SUCCESS")
        sys.exit(0)
