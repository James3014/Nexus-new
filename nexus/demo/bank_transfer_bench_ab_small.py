import time
import threading

class Account:
    def __init__(self, balance):
        self.balance = balance
        self.lock = threading.Lock()

def transfer(acc1, acc2, amount):
    first, second = (acc1, acc2) if id(acc1) < id(acc2) else (acc2, acc1)
    with first.lock:
        time.sleep(0.01)  # Simulate some IO or DB operation
        with second.lock:
            if acc1.balance >= amount:
                acc1.balance -= amount
                acc2.balance += amount
