import time

class RateLimiter:
    def __init__(self, limit=2, window_sec=1.0):
        self.limit = limit
        self.window_sec = window_sec
        self.hits = []

    def allow(self):
        now = time.time()
        self.hits = [hit for hit in self.hits if now - hit < self.window_sec]
        if len(self.hits) >= self.limit:
            return False
        self.hits.append(now)
        return True
