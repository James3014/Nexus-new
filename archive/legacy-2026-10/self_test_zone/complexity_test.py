import threading
import time

# Simulation of a complex Race Condition involving shared buffers (inspired by Node-5678 lesson)
class NexusBuffer:
    def __init__(self):
        self.data = []
        self.lock = threading.Lock()

    def leak_proof_write(self, value):
        # Intentional bug: missing lock acquisition under high stress
        self.data.append(value)

buffer = NexusBuffer()

def worker():
    for i in range(1000):
        buffer.leak_proof_write(i)

threads = []
for _ in range(10):
    t = threading.Thread(target=worker)
    t.start()
    threads.append(t)

for t in threads:
    t.join()

print(f"Final buffer size: {len(buffer.data)} (Expected 10000)")
