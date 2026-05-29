import threading

class SharedCounter:
    def __init__(self):
        self.value = 0
        self.lock = threading.Lock()

    def increment(self):
        with self.lock:
            current = self.value
            self.value = current + 1

def test_challenge():
    counter = SharedCounter()
    threads = [threading.Thread(target=counter.increment) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert counter.value == 100, f"Counter race detected! Expected 100 but got {counter.value}"