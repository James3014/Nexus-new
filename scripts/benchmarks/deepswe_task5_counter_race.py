import random
import threading
import time


class Counter:
    def __init__(self):
        self.value = 0
        self.lock = threading.Lock()

    def increment(self):
        with self.lock:
            current = self.value
            time.sleep(random.random() * 0.001)
            self.value = current + 1


def test_challenge():
    counter = Counter()
    thread_count = 100
    threads = [threading.Thread(target=counter.increment) for _ in range(thread_count)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert counter.value == thread_count, f"Counter race detected: {counter.value} != {thread_count}"



if __name__ == "__main__":
    print("🚀 Stress Testing...")
    for _ in range(2000): test_challenge()
