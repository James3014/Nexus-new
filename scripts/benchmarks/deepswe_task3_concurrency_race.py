import threading
import time
import sys

class ThreadSafeDict:
    def __init__(self):
        self.data = {}
        self.lock = threading.Lock()

    def update(self, key, val):
        with self.lock:
            temp = self.data.get(key, 0)
            time.sleep(0.0001)
            self.data[key] = temp + val

def test_challenge():
    d = ThreadSafeDict()
    
    def worker():
        for _ in range(50):
            d.update("counter", 1)

    threads = []
    for _ in range(5):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    if d.data.get("counter", 0) != 250:
        print(f"FAILED: Expected 250, got {d.data.get('counter')}")
        return False
    return True

if __name__ == "__main__":
    if not test_challenge():
        sys.exit(1)
    else:
        print("SUCCESS")
        sys.exit(0)
