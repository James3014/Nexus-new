import threading
import time

class ConnectionPool:
    def __init__(self, max_connections=5):
        self.max_connections = max_connections
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            if self.active < self.max_connections:
                time.sleep(0.001)  # Race window
                self.active += 1
                if self.active > self.peak:
                    self.peak = self.active
                return True
        return False

    def release(self):
        with self.lock:
            self.active -= 1

def test_challenge():
    pool = ConnectionPool(max_connections=5)
    acquired = []

    def worker():
        if pool.acquire():
            acquired.append(1)
            time.sleep(0.01)
            pool.release()

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert pool.peak <= 5, f"Connection pool race! Peak connections exceeded limit: {pool.peak} > 5"