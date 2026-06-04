"""Task 8: Concurrent Transaction Commit/Rollback Race (ABA Problem)"""
import threading
import time

class TransactionLog:
    def __init__(self):
        self.balance = 1000
        self.transactions = []
        self.lock = threading.Lock()

    def transfer(self, amount, destination):
        # Fixed: use lock to ensure read-check-write is atomic
        with self.lock:
            if self.balance >= amount:
                time.sleep(0.001)  # Simulate DB latency / race window
                self.balance -= amount
                self.transactions.append({"to": destination, "amount": amount})

def test_challenge():
    log = TransactionLog()

    def do_transfer():
        log.transfer(600, "account_B")

    # Two concurrent transfers of 600 each - only one should succeed
    t1 = threading.Thread(target=do_transfer)
    t2 = threading.Thread(target=do_transfer)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert log.balance >= 0, f"Transaction ABA race detected! Balance went negative: {log.balance}"
    assert len(log.transactions) <= 1, f"Double-spend race! {len(log.transactions)} transactions committed with only 1000 balance"

if __name__ == "__main__":
    print("🚀 Stress Testing...")
    for _ in range(2000): test_challenge()
