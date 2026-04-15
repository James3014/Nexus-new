import time
from nexus.research.local_sprint_mutator import generate_local_candidate

source = """import time

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
"""
task = "feature-rate-limiter"
patched = generate_local_candidate(source, task, "", 0)

with open("nexus/demo/feature_rate_limiter_patched.py", "w") as f:
    f.write(patched)

print("Patched source:")
print(patched)
