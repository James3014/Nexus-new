import threading
from nexus.demo.bank_transfer_bench_ab_stress import Account, transfer

def test_no_deadlock_stress():
    acc1 = Account(100)
    acc2 = Account(100)
    def thread1():
        for _ in range(50):
            transfer(acc1, acc2, 1)
    def thread2():
        for _ in range(50):
            transfer(acc2, acc1, 1)
    t1 = threading.Thread(target=thread1, daemon=True)
    t2 = threading.Thread(target=thread2, daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=2.0)
    t2.join(timeout=2.0)
    assert not t1.is_alive(), "Deadlock detected in thread 1"
    assert not t2.is_alive(), "Deadlock detected in thread 2"
    assert acc1.balance + acc2.balance == 200
