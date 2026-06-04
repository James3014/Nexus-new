import threading
import time

class BuggyIdempotentExecutor:
    """模擬重試冪等性失效 (Double Execution)"""
    def __init__(self):
        self.executed = False
        self.call_count = 0

    def execute(self):
        if not self.executed:
            time.sleep(0.01) # Race window
            self.call_count += 1
            self.executed = True

class BuggyTokenBucket:
    """模擬 Rate Limiter Token Bucket 競爭 (超發)"""
    def __init__(self, capacity=10):
        self.tokens = capacity

    def consume(self):
        if self.tokens > 0:
            time.sleep(0.001)
            self.tokens -= 1
            return True
        return False

class BuggyReadWriteRegistry:
    """模擬讀寫鎖失效 (Data Tear / Inconsistent Read)"""
    def __init__(self):
        self.data = {"A": 0, "B": 0}

    def write(self, val: int):
        self.data["A"] = val
        time.sleep(0.01) # 寫入過程被打斷
        self.data["B"] = val

    def read(self):
        # 預期 A 和 B 永遠相等
        return self.data["A"] == self.data["B"]

class BuggyProducerConsumer:
    """模擬 Queue 的丟失與競爭"""
    def __init__(self):
        self.queue = []
    
    def produce(self, item):
        time.sleep(0.001)
        self.queue.append(item)

    def consume(self):
        if len(self.queue) > 0:
            time.sleep(0.001)
            return self.queue.pop(0)
        return None

class BuggyAsyncBarrier:
    """模擬 Wait Group 提早放行"""
    def __init__(self, count):
        self.count = count

    def done(self):
        time.sleep(0.001)
        self.count -= 1

    def wait(self):
        while self.count > 0:
            time.sleep(0.001)
