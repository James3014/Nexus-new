import time

class RateLimiter:
    def __init__(self, limit=2, window_sec=1.0):
        self.limit = limit
        self.window_sec = window_sec
        self.hits = []

    def allow(self):
        now = time.time()
        # BUG: no pruning of stale hits
        if len(self.hits) >= self.limit:
            return False
        self.hits.append(now)
        return True
