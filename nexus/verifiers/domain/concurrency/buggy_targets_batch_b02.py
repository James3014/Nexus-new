import threading
import time
from nexus.verifiers.domain.common_core.state_guards import execute_with_double_checked_lock

class BuggyIdempotentExecutor:
    """模擬重試冪等性失效 (Double Execution)"""
    def __init__(self):
        self.executed = False
        self.call_count = 0
        self._lock = threading.Lock()

    def execute(self):
        if not self.executed:
            time.sleep(0.01) # Race window
            self.call_count += 1
            self.executed = True

class BuggyTokenBucket:
    """模擬 Rate Limiter Token Bucket 競爭 (超發)"""
    def __init__(self, capacity=10):
        self.tokens = capacity
        self._lock = threading.Lock()

    def consume(self):
        with self._lock:
            if self.tokens > 0:
                time.sleep(0.001)
                self.tokens -= 1
                return True
            return False

class BuggyReadWriteRegistry:
    """模擬讀寫鎖失效 (Data Tear / Inconsistent Read)"""
    def __init__(self):
        self.data = {"A": 0, "B": 0}
        self._lock = threading.Lock()

    def write(self, val: int):
        with self._lock:
            self.data["A"] = val
            time.sleep(0.01) # 寫入過程被打斷
            self.data["B"] = val

    def read(self):
        with self._lock:
            # 預期 A 和 B 永遠相等
            return self.data["A"] == self.data["B"]

class BuggyProducerConsumer:
    """模擬 Queue 的丟失與競爭"""
    def __init__(self):
        self.queue = []
        self._cond = threading.Condition()
    
    def produce(self, item):
        with self._cond:
            time.sleep(0.001)
            self.queue.append(item)
            self._cond.notify()

    def consume(self):
        with self._cond:
            while len(self.queue) == 0:
                self._cond.wait()
            time.sleep(0.001)
            return self.queue.pop(0)

class BuggyAsyncBarrier:
    """模擬 Wait Group 提早放行"""
    def __init__(self, count):
        self.count = count
        self._cond = threading.Condition()

    def done(self):
        with self._cond:
            time.sleep(0.001)
            self.count -= 1
            if self.count == 0:
                self._cond.notify_all()

    def wait(self):
        with self._cond:
            while self.count > 0:
                self._cond.wait()
