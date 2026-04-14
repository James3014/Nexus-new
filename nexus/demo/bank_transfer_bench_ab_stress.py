import time
import threading

class Account:
    def __init__(self, balance):
        self.balance = balance
        self.lock = threading.Lock()

def transfer(acc1, acc2, amount):
    with acc1.lock:
        time.sleep(0.01) # Simulate some IO or DB operation
        with acc2.lock:
            if acc1.balance >= amount:
                acc1.balance -= amount
                acc2.balance += amount
