import threading
import time

class BuggyThunderingHerdCache:
    """模擬 Cache Stampede (Thundering Herd)"""
    def __init__(self):
        self._cache = {}
        self.compute_count = 0

    def get(self, key: str):
        if key not in self._cache:
            time.sleep(0.01) # Simulate expensive DB query
            self._cache[key] = f"DATA_FOR_{key}"
            self.compute_count += 1
        return self._cache[key]

class BuggyConnectionPool:
    """模擬資源池並發釋放競爭 (Resource Leak)"""
    def __init__(self, size=5):
        self.pool = [f"conn_{i}" for i in range(size)]
        self.in_use = 0

    def acquire(self):
        if len(self.pool) > 0:
            time.sleep(0.001) # Race window
            conn = self.pool.pop()
            self.in_use += 1
            return conn
        return None

    def release(self, conn):
        time.sleep(0.001) # Race window
        self.pool.append(conn)
        self.in_use -= 1
